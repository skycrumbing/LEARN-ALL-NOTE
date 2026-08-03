/**
 * 导航算法实现：A* + Contraction Hierarchies（收缩层次）
 *
 * 这个文件模拟了高德地图导航的核心算法思路，从简单到复杂逐步实现：
 *
 * 1. Graph（图）—— 道路网络的基础数据结构
 * 2. Dijkstra —— 最短路径的基准算法
 * 3. AStar —— 带启发式搜索的优化
 * 4. ContractionHierarchies —— 工业级加速（预处理 + 快速查询）
 * 5. NavigationEngine —— 整合所有功能
 *
 * 作者：AI 学习笔记
 */

import java.util.*;

// ============================================================
// 1. 基础数据结构
// ============================================================

/**
 * 图中的节点（Node）
 *
 * 每个节点代表一个道路交叉口或道路上的一个点。
 * 在真实导航中，一个节点包含经纬度坐标，这里用 id 和 x/y 简化模拟。
 */
class Node {
    int id;           // 节点唯一标识
    double x, y;      // 模拟坐标（真实场景是经纬度）
    String name;      // 节点名称（如"天安门"、"西直门桥"）

    Node(int id, double x, double y, String name) {
        this.id = id;
        this.x = x;
        this.y = y;
        this.name = name;
    }

    /**
     * 计算到另一个节点的欧几里得距离（直线距离）
     * 在 A* 中作为启发式函数（heuristic）使用
     */
    double distanceTo(Node other) {
        double dx = this.x - other.x;
        double dy = this.y - other.y;
        return Math.sqrt(dx * dx + dy * dy);
    }

    @Override
    public String toString() {
        return name + "(" + id + ")";
    }
}

/**
 * 图中的边（Edge）
 *
 * 代表两个节点之间的一条道路。
 * weight 可以是距离（米）、时间（秒）或综合成本。
 */
class Edge {
    int from;            // 起点节点 id
    int to;              // 终点节点 id
    double weight;       // 通过这条边的代价（距离/时间）
    String roadName;     // 道路名称（"京藏高速"、"长安街"等）
    int level;           // 道路层级：0=小区路, 1=城市路, 2=高速

    Edge(int from, int to, double weight, String roadName, int level) {
        this.from = from;
        this.to = to;
        this.weight = weight;
        this.roadName = roadName;
        this.level = level;
    }

    @Override
    public String toString() {
        return roadName + "(" + weight + ")";
    }
}

/**
 * 路径搜索中的一个状态
 * 用于 Dijkstra 和 A* 的优先队列中
 */
class PathNode implements Comparable<PathNode> {
    int nodeId;            // 当前到达的节点
    double gScore;         // 从起点到当前节点的实际距离（g）
    double fScore;         // 预估总距离（g + h），用于 A*
    List<Integer> path;    // 从起点到当前节点的路径节点列表

    PathNode(int nodeId, double gScore, double fScore, List<Integer> path) {
        this.nodeId = nodeId;
        this.gScore = gScore;
        this.fScore = fScore;
        this.path = new ArrayList<>(path);
        this.path.add(nodeId);
    }

    /**
     * PriorityQueue 需要按 fScore 排序，fScore 最小的优先出队
     */
    @Override
    public int compareTo(PathNode other) {
        return Double.compare(this.fScore, other.fScore);
    }
}

// ============================================================
// 2. 道路网络（Graph）
// ============================================================

/**
 * 有向图，表示道路网络
 *
 * 支持：
 *  - 添加节点和边
 *  - 获取邻居
 *  - 层级过滤（只搜索高速路，忽略小区路）
 *  - 图的深拷贝（用于 CH 预处理时添加捷径边）
 */
class Graph {
    // 邻接表：每个节点对应的出边列表
    Map<Integer, List<Edge>> adjacencyList;
    // 所有节点映射：id -> Node
    Map<Integer, Node> nodes;

    Graph() {
        this.adjacencyList = new HashMap<>();
        this.nodes = new HashMap<>();
    }

    /**
     * 添加一个节点
     */
    void addNode(Node node) {
        nodes.put(node.id, node);
        adjacencyList.putIfAbsent(node.id, new ArrayList<>());
    }

    /**
     * 添加一条有向边（from -> to）
     * 如果是双向道路，需要调用两次
     */
    void addEdge(int from, int to, double weight, String roadName, int level) {
        adjacencyList.computeIfAbsent(from, k -> new ArrayList<>());
        adjacencyList.get(from).add(new Edge(from, to, weight, roadName, level));
    }

    /**
     * 添加双向道路
     */
    void addBidirectionalEdge(int a, int b, double weight, String roadName, int level) {
        addEdge(a, b, weight, roadName, level);
        addEdge(b, a, weight, roadName, level);
    }

    /**
     * 获取从某个节点出发的所有出边
     */
    List<Edge> getNeighbors(int nodeId) {
        return adjacencyList.getOrDefault(nodeId, new ArrayList<>());
    }

    /**
     * 获取某个节点
     */
    Node getNode(int nodeId) {
        return nodes.get(nodeId);
    }

    /**
     * 深拷贝：创建一个新的图，复制所有节点和边
     * 用于 CH 预处理，因为预处理会在原图上添加捷径边
     */
    Graph deepCopy() {
        Graph copy = new Graph();
        for (Node node : nodes.values()) {
            copy.addNode(new Node(node.id, node.x, node.y, node.name));
        }
        for (List<Edge> edges : adjacencyList.values()) {
            for (Edge e : edges) {
                copy.addEdge(e.from, e.to, e.weight, e.roadName, e.level);
            }
        }
        return copy;
    }

    /**
     * 获取节点数量
     */
    int nodeCount() {
        return nodes.size();
    }

    /**
     * 获取边数量
     */
    int edgeCount() {
        return adjacencyList.values().stream().mapToInt(List::size).sum();
    }
}

// ============================================================
// 3. Dijkstra 最短路径算法
// ============================================================

/**
 * Dijkstra 算法：最短路径的基准
 *
 * 思路：每次从"未处理的节点"中选距离起点最近的，扩展它，更新邻居距离。
 * 特点：保证找到最短路径，但搜索方向是"均匀向外扩散"。
 *
 * 时间复杂度：O((V + E) log V)  使用优先队列
 */
class Dijkstra {
    private Graph graph;

    Dijkstra(Graph graph) {
        this.graph = graph;
    }

    /**
     * 计算从 startId 到 endId 的最短路径
     *
     * @return 搜索结果，包含路径和距离
     */
    SearchResult findShortestPath(int startId, int endId) {
        // 距离表：startId -> 每个节点的最短距离
        Map<Integer, Double> distances = new HashMap<>();
        // 前驱节点表：用于回溯路径
        Map<Integer, Integer> previous = new HashMap<>();
        // 是否已访问
        Set<Integer> visited = new HashSet<>();

        // 优先队列，按当前距离排序
        // [节点id, 当前距离]
        PriorityQueue<double[]> pq = new PriorityQueue<>(
            Comparator.comparingDouble(a -> a[1])
        );

        // 初始化
        distances.put(startId, 0.0);
        pq.offer(new double[]{startId, 0.0});

        // 记录搜索过程（用于调试和可视化）
        List<Integer> exploredNodes = new ArrayList<>();

        while (!pq.isEmpty()) {
            double[] current = pq.poll();
            int currentNodeId = (int) current[0];
            double currentDist = current[1];

            // 如果已经找到终点，提前结束
            if (currentNodeId == endId) {
                break;
            }

            // 如果这个节点已经被访问过了，跳过（优先队列中可能有旧记录）
            if (visited.contains(currentNodeId)) {
                continue;
            }
            visited.add(currentNodeId);
            exploredNodes.add(currentNodeId);

            // 扩展当前节点：遍历所有出边
            for (Edge edge : graph.getNeighbors(currentNodeId)) {
                int neighborId = edge.to;
                double newDist = currentDist + edge.weight;

                // 如果找到了更短的路径到 neighbor，更新
                if (newDist < distances.getOrDefault(neighborId, Double.MAX_VALUE)) {
                    distances.put(neighborId, newDist);
                    previous.put(neighborId, currentNodeId);
                    pq.offer(new double[]{neighborId, newDist});
                }
            }
        }

        // 回溯路径
        return reconstructPath(startId, endId, previous, distances, exploredNodes);
    }

    /**
     * 从前驱节点表回溯路径
     */
    SearchResult reconstructPath(int startId, int endId, Map<Integer, Integer> previous,
                                  Map<Integer, Double> distances, List<Integer> exploredNodes) {
        List<Integer> path = new ArrayList<>();
        int currentNode = endId;

        // 从终点往回走，直到起点
        while (currentNode != startId) {
            path.add(currentNode);
            currentNode = previous.get(currentNode);
            if (currentNode == -1 || currentNode == 0) { // 防止死循环
                // 没有找到路径
                return new SearchResult(Collections.emptyList(), Double.MAX_VALUE, exploredNodes.size());
            }
        }
        path.add(startId);
        Collections.reverse(path); // 反转，从起点到终点

        double totalDistance = distances.getOrDefault(endId, Double.MAX_VALUE);
        return new SearchResult(path, totalDistance, exploredNodes.size());
    }
}

// ============================================================
// 4. A* 算法（A-Star）
// ============================================================

/**
 * A* 搜索算法
 *
 * 核心改进：在 Dijkstra 的基础上加上"启发式函数"（heuristic），
 * 让搜索更有方向性，而不是均匀地向四周扩散。
 *
 * 公式：f(n) = g(n) + h(n)
 *   g(n) = 从起点到节点 n 的实际距离
 *   h(n) = 从节点 n 到终点的估计距离（启发式）
 *   f(n) = 经过节点 n 的预估总距离
 *
 * 关键：h(n) 必须 ≤ 实际距离（可采纳性），才能保证找到最短路径。
 *       这里用直线距离，因为两点之间直线最短，所以 h(n) ≤ 实际道路距离 ✅
 */
class AStar {
    private Graph graph;

    AStar(Graph graph) {
        this.graph = graph;
    }

    /**
     * 计算从 startId 到 endId 的最短路径
     */
    SearchResult findShortestPath(int startId, int endId) {
        Node startNode = graph.getNode(startId);
        Node endNode = graph.getNode(endId);

        if (startNode == null || endNode == null) {
            return new SearchResult(Collections.emptyList(), Double.MAX_VALUE, 0);
        }

        // gScore：从起点到每个节点的实际最短距离
        Map<Integer, Double> gScore = new HashMap<>();
        // 前驱节点
        Map<Integer, Integer> previous = new HashMap<>();
        // 已访问集合
        Set<Integer> visited = new HashSet<>();

        // 优先队列，按 fScore = gScore + heuristic 排序
        PriorityQueue<PathNode> openSet = new PriorityQueue<>();

        // 初始化
        gScore.put(startId, 0.0);
        double heuristic = startNode.distanceTo(endNode);
        openSet.offer(new PathNode(startId, 0.0, heuristic, new ArrayList<>()));

        int exploredCount = 0;

        while (!openSet.isEmpty()) {
            PathNode current = openSet.poll();
            int currentNodeId = current.nodeId;

            // 到达终点
            if (currentNodeId == endId) {
                return new SearchResult(current.path, current.gScore, exploredCount);
            }

            // 已访问过，跳过
            if (visited.contains(currentNodeId)) {
                continue;
            }
            visited.add(currentNodeId);
            exploredCount++;

            // 扩展当前节点
            for (Edge edge : graph.getNeighbors(currentNodeId)) {
                int neighborId = edge.to;
                if (visited.contains(neighborId)) {
                    continue;
                }

                double tentativeG = gScore.get(currentNodeId) + edge.weight;

                // 如果找到更短的路径
                if (tentativeG < gScore.getOrDefault(neighborId, Double.MAX_VALUE)) {
                    gScore.put(neighborId, tentativeG);
                    previous.put(neighborId, currentNodeId);

                    // 计算 fScore = gScore + heuristic
                    Node neighbor = graph.getNode(neighborId);
                    double h = neighbor.distanceTo(endNode);
                    double f = tentativeG + h;

                    openSet.offer(new PathNode(neighborId, tentativeG, f, current.path));
                }
            }
        }

        // 没有找到路径
        return new SearchResult(Collections.emptyList(), Double.MAX_VALUE, exploredCount);
    }

    /**
     * 带层级过滤的 A* 搜索
     *
     * 模拟高德地图的分层路网策略：
     * 1. 在起点附近用低层级道路（小区路、城市路）
     * 2. 远距离切换到高层级道路（高速）
     * 3. 到终点附近再切回低层级道路
     *
     * @param minLevel 最低道路层级（0=所有路, 1=城市路以上, 2=高速）
     */
    SearchResult findShortestPathWithLevel(int startId, int endId, int minLevel) {
        Node startNode = graph.getNode(startId);
        Node endNode = graph.getNode(endId);

        // ... 与上面基本相同的逻辑，但只走 level >= minLevel 的道路
        // 这里为了简洁，省略重复代码，实际使用时会在 getNeighbors 时过滤

        return findShortestPath(startId, endId);
    }
}

// ============================================================
// 5. Contraction Hierarchies（收缩层次）
// ============================================================

/**
 * Contraction Hierarchies (CH) —— 工业级导航核心加速技术
 *
 * 思路：在导航之前，先把图"预处理"好，添加一些"捷径边"，
 * 这样在真正导航时，搜索空间会大大缩小。
 *
 * 类比：
 *   你从北京去上海，不需要查每个县城的路怎么走。
 *   CH 相当于提前算好了"从北京到上海走高速，中间经过这些城市"，
 *   把细节收缩掉了，只保留关键节点之间的捷径。
 *
 * 预处理步骤：
 *   1. 给每个节点算一个"重要性"分数
 *   2. 按重要性从低到高"收缩"节点
 *   3. 收缩时，检查邻居之间是否需要添加捷径边
 *   4. 处理完所有节点，得到一个新的图（原图 + 捷径）
 *
 * 查询步骤：
 *   1. 从起点和终点同时向上搜索（只走重要性更高的节点）
 *   2. 在中途相遇，拼接路径
 */
class ContractionHierarchies {
    // 原始图（在预处理过程中会被添加上捷径边）
    private Graph graph;
    // 每个节点的"重要性"排名（越高越重要）
    private Map<Integer, Integer> nodeOrder;
    // 捷径边信息（用于调试和可视化）
    private List<String> shortcutsAdded;

    ContractionHierarchies(Graph graph) {
        // 深拷贝，不修改原始图
        this.graph = graph.deepCopy();
        this.nodeOrder = new HashMap<>();
        this.shortcutsAdded = new ArrayList<>();
    }

    /**
     * 执行预处理
     *
     * 这是 CH 最核心的部分，分两步：
     *
     * 第一步：计算每个节点的"重要性"
     *   重要性 = 该节点被多少条最短路径经过（介数中心性）
     *   简单实现：用节点的度数（连接的边数）作为近似
     *
     * 第二步：按重要性从低到高收缩节点
     *   收缩一个节点时：
     *     1. 暂时删除这个节点
     *     2. 检查它的邻居之间是否需要捷径
     *     3. 如果邻居之间的最短路径经过这个节点，则添加一条捷径
     *
     * @param shortcutWeight 捷径边的权重（通常比实际路径稍大，保留原始路径的优先性）
     */
    void preprocess(double shortcutWeight) {
        System.out.println("===== CH 预处理开始 =====");
        System.out.println("节点数: " + graph.nodeCount() + ", 边数: " + graph.edgeCount());

        // 第一步：计算每个节点的重要性
        // 用"边数 × 邻居重要性"作为重要性分数
        // 实际 CH 使用更复杂的指标（边的差异度、介数中心性等）
        Map<Integer, Double> importance = new HashMap<>();
        for (Node node : graph.nodes.values()) {
            List<Edge> neighbors = graph.getNeighbors(node.id);
            double score = neighbors.size(); // 度数作为重要性
            importance.put(node.id, score);
        }

        // 按重要性排序（不重要 → 重要）
        List<Integer> sortedNodes = new ArrayList<>(graph.nodes.keySet());
        sortedNodes.sort(Comparator.comparingDouble(importance::get));
        System.out.println("节点重要性排序完成");

        // 第二步：按重要性从低到高收缩节点
        int order = 0;
        for (int nodeId : sortedNodes) {
            // 给这个节点分配一个"等级"（order 越小越不重要）
            nodeOrder.put(nodeId, order++);
            contractNode(nodeId, shortcutWeight);
        }

        System.out.println("预处理完成！添加了 " + shortcutsAdded.size() + " 条捷径边");
        System.out.println("新边数: " + graph.edgeCount());
        System.out.println("==========================");
    }

    /**
     * 收缩一个节点
     *
     * 收缩节点 v 时：
     *   1. 获取 v 的所有邻居（入边和出边）
     *   2. 对每一对邻居 (u, w)，检查 u 到 w 的最短路径是否经过 v
     *   3. 如果是，在 u 和 w 之间添加一条捷径边
     *   4. 删除 v 及其所有边
     *
     * 这样，v 被"隐藏"了，但它的信息被保留在捷径中。
     */
    /**
     * 收缩一个节点（Contract Node）
     *
     * 这是 CH 算法最核心的操作。理解了这个方法，就理解了 CH 的一半。
     *
     * ────────────────────────────────────────────────────────────
     * 核心思想：如果一个节点是"不重要的"（比如小巷子交叉口），
     * 我们可以把它从图中"隐藏"掉，但必须保证隐藏后最短路径仍然正确。
     * 为了做到这一点，需要给它的邻居之间添加"捷径边"（shortcut）。
     * ────────────────────────────────────────────────────────────
     *
     * 具体来说，收缩节点 v 时，考虑它的每一对邻居 (u, w)：
     *
     *    收缩前：u ───→ v ───→ w
     *    收缩后：u ════════→ w （捷径边）
     *
     * 如果 u 到 w 的"最短路径"经过 v（即 u→v→w 比 u→w 的直接路径短），
     * 则在 u 和 w 之间添加一条"捷径边"，权重为 u→v + v→w。
     * 这样，即使 v 被隐藏了，从 u 到 w 的最短路径信息仍然保留在捷径中。
     *
     * 类比：你从北京去上海，中间经过济南。
     *       收缩济南后，北京和上海之间多了一条"捷径"（京沪高速直达）。
     *       以后从北京到上海就不用再考虑济南了，直接走捷径。
     *
     * ────────────────────────────────────────────────────────────
     * 为什么需要这个操作？
     *
     * 假设不添加捷径，直接删除节点 v：
     *   - 原来 u → v → w 的路径（权重 10）就断了
     *   - u 到 w 还有一条绕路（权重 100），但用户不知道
     *   - 以后查询 u → w 的最短路径，结果会变成 100，而不是正确的 10
     *   - 这就错了！
     *
     * 添加捷径（权重 10）后：
     *   - u → w 的最短路径仍然是 10 ✅
     *   - 而 v 被"隐藏"了，以后搜索时不用考虑它，搜索空间变小了
     *
     * ────────────────────────────────────────────────────────────
     * 逐步执行流程：
     *
     * 1. 获取节点 v 的所有邻居（出边列表）
     * 2. 对每一对邻居 (u, w)：
     *    a. 计算 u → v → w 的路径权重：pathThroughV = inEdge.weight + outEdge.weight
     *    b. 检查 u 到 w 是否有直接路径
     *    c. 如果有直接路径，比较两者谁更短
     *    d. 如果没有直接路径，或者 u→v→w 更短，则添加捷径边
     * 3. 删除节点 v 的所有出边（v 被"收缩"掉了）
     */
    private void contractNode(int nodeId, double shortcutWeight) {
        Node node = graph.getNode(nodeId);
        if (node == null) return;

        // ── 第一步：获取节点 v 的邻居列表 ──
        // incidentEdges 是 v 的所有出边，即 v 可以到达这些邻居
        // 在无向图中，v 的入边和出边是相同的集合
        List<Edge> incidentEdges = graph.getNeighbors(nodeId);

        // ── 第二步：遍历所有邻居对 (u, w) ──
        // 外层循环：取一个邻居 u（通过入边到达 u）
        // 内层循环：取另一个邻居 w（通过出边到达 w）
        // 组合起来就是 u → v → w 的路径
        for (Edge inEdge : incidentEdges) {
            int u = inEdge.to;  // 第一个邻居（"入边"的起点）
            if (u == nodeId) continue;  // 跳过自己

            for (Edge outEdge : incidentEdges) {
                int w = outEdge.to;  // 第二个邻居（"出边"的终点）
                if (w == nodeId || w == u) continue;  // 跳过自己和重复的邻居

                // ── 第三步：计算 u → v → w 的路径权重 ──
                // 如果 u 和 w 之间没有直接路径，或者 u→v→w 比直接路径更短，
                // 就需要在 u 和 w 之间添加一条捷径边
                double pathThroughV = inEdge.weight + outEdge.weight;

                // ── 第四步：检查 u 到 w 是否有直接路径 ──
                //
                // 这个循环的作用是：遍历 u 的所有出边，找到终点为 w 的那条边。
                // 找到了 → hasDirectPath = true, directPathWeight = 该边的权重
                // 没找到 → hasDirectPath = false, directPathWeight = MAX_VALUE
                //
                // 注意：这里是 Java 版的内联实现，没有单独的 getEdgeWeight() 方法。
                // 和 amap-navigation.md 中的 getEdgeWeight() 是等价的，逻辑完全相同。
                //
                // 为什么要做这一步？因为我们在判断"是否需要添加捷径"：
                //   - 如果 u 到 w 没有直接路径，u→v→w 就是唯一的连接，必须加捷径
                //   - 如果 u 到 w 有直接路径，还要比较谁更短
                //
                // 例子：北京(1) → 天津(2) → 济南(3)
                //   收缩节点 2（天津），u=北京(1)，w=济南(3)
                //   遍历北京的出边：
                //     北京 → 天津（权重 12） → 终点不是济南(3)，跳过
                //     北京 → 廊坊（权重 8）  → 终点不是济南(3)，跳过
                //     ... 遍历完毕，没有找到北京 → 济南的直接边
                //   → hasDirectPath = false
                //
                //   另例：如果图里有"北京 → 济南"的直接路径（权重 100）
                //     遍历北京的出边：
                //       北京 → 济南（权重 100） → 终点是济南(3)！
                //     → hasDirectPath = true, directPathWeight = 100
                //     → 然后比较：pathThroughV(42) < directPathWeight(100)
                //       → 42 < 100，走天津更近 → 添加捷径
                //
                // 为什么直接在这里做循环，而不是单独的 getEdgeWeight() 方法？
                // 因为 Java 版的实现中，hasDirectPath 和 directPathWeight
                // 是配合使用的：先找路径，再判断是否存在。
                // 如果拆成单独方法，需要调用两次，效率更低。
                //
                // 时间复杂度：O(degree(u))，通常 < 10，非常快
                boolean hasDirectPath = false;
                double directPathWeight = Double.MAX_VALUE;
                for (Edge e : graph.getNeighbors(u)) {
                    if (e.to == w) {
                        hasDirectPath = true;
                        directPathWeight = e.weight;
                        break;
                    }
                }

                // ── 第五步：判断是否需要添加捷径 ──
                // 两种情况需要添加捷径：
                //   情况 A：u 和 w 之间没有直接路径（hasDirectPath == false）
                //     → 如果不加捷径，隐藏 v 后 u 到 w 就断了
                //   情况 B：u→v→w 比 u→w 的直接路径更短
                //     → 如果不加捷径，隐藏 v 后 u→w 的最短路径就丢了
                //
                // 举个例子：
                //   北京(1) → 天津(2) 权重 12
                //   天津(2) → 济南(3) 权重 30
                //   北京(1) → 济南(3) 没有直接路径
                //
                //   收缩节点 2（天津）时：
                //     pathThroughV = 12 + 30 = 42
                //     北京到济南没有直接路径 → 需要添加捷径
                //     添加：北京(1) → 济南(3) 权重 42
                //
                //   以后要从北京到济南，直接走捷径，不用再经过天津了
                if (!hasDirectPath || pathThroughV < directPathWeight) {
                    String shortcutName = "捷径(" + graph.getNode(u).name + "→" + graph.getNode(w).name + ")";
                    // 捷径权重乘以 shortcutWeight 系数，通常为 1.0
                    // 可以稍微调大一点，让原始路径优先于捷径（防止路径退化）
                    graph.addEdge(u, w, pathThroughV * shortcutWeight, shortcutName, 2);
                    shortcutsAdded.add("捷径: " + graph.getNode(u).name + " ─→ " + graph.getNode(w).name
                        + " (原经 " + graph.getNode(nodeId).name + ", 权重 " + pathThroughV + ")");
                }
            }
        }

        // ── 第六步：删除节点 v 的所有出边 ──
        // 节点 v 已经被"收缩"了，它的信息被保存在捷径边中
        // 以后搜索时，不会再经过 v（因为它的出边被删了）
        // 但 u → w 的捷径仍然存在，最短路径信息不会丢失
        //
        // 类比：济南被"隐藏"了，但北京到上海的直达高速还在
        graph.adjacencyList.get(nodeId).clear();
    }

    /**
     * 使用 CH 进行快速查询
     *
     * 从起点和终点同时向上搜索（只走重要性更高的节点），
     * 在中途相遇。
     *
     * 这比全图搜索快得多，因为：
     *  - 搜索空间被限制在"重要节点"
     *  - 捷径让长距离移动一步到位
     */
    SearchResult query(int startId, int endId) {
        // 前向搜索（从起点出发）
        Map<Integer, Double> forwardDist = new HashMap<>();
        Map<Integer, Integer> forwardPrev = new HashMap<>();
        PriorityQueue<double[]> forwardPQ = new PriorityQueue<>(
            Comparator.comparingDouble(a -> a[1])
        );

        // 反向搜索（从终点出发）
        Map<Integer, Double> backwardDist = new HashMap<>();
        Map<Integer, Integer> backwardPrev = new HashMap<>();
        PriorityQueue<double[]> backwardPQ = new PriorityQueue<>(
            Comparator.comparingDouble(a -> a[1])
        );

        // 初始化
        forwardDist.put(startId, 0.0);
        forwardPQ.offer(new double[]{startId, 0.0});
        backwardDist.put(endId, 0.0);
        backwardPQ.offer(new double[]{endId, 0.0});

        // 相遇点
        int meetingNode = -1;
        double bestDistance = Double.MAX_VALUE;

        // 已访问集合
        Set<Integer> forwardVisited = new HashSet<>();
        Set<Integer> backwardVisited = new HashSet<>();

        int iterations = 0;

        // 交替搜索，直到相遇或搜索空间耗尽
        while (!forwardPQ.isEmpty() && !backwardPQ.isEmpty()) {
            iterations++;

            // 前向搜索一步
            if (!forwardPQ.isEmpty()) {
                double[] fCurrent = forwardPQ.poll();
                int fNode = (int) fCurrent[0];
                double fDist = fCurrent[1];

                if (forwardVisited.contains(fNode)) continue;
                forwardVisited.add(fNode);

                // 只走重要性更高的节点（向上搜索）
                for (Edge edge : graph.getNeighbors(fNode)) {
                    int neighbor = edge.to;
                    // 关键：只走重要性更高的节点
                    // 如果 neighbor 的重要性 <= 当前节点，跳过（让反向搜索处理）
                    if (nodeOrder.getOrDefault(neighbor, 0) <= nodeOrder.getOrDefault(fNode, 0)) {
                        if (forwardDist.containsKey(neighbor)) continue;
                    }

                    double newDist = fDist + edge.weight;
                    if (newDist < forwardDist.getOrDefault(neighbor, Double.MAX_VALUE)) {
                        forwardDist.put(neighbor, newDist);
                        forwardPrev.put(neighbor, fNode);
                        forwardPQ.offer(new double[]{neighbor, newDist});
                    }
                }

                // 检查是否与反向搜索相遇
                if (backwardDist.containsKey(fNode)) {
                    double total = fDist + backwardDist.get(fNode);
                    if (total < bestDistance) {
                        bestDistance = total;
                        meetingNode = fNode;
                    }
                }
            }

            // 反向搜索一步
            // 反向搜索需要在反向图上进行，这里简化：用相同逻辑
            // 实际 CH 需要构建反向图（入边变为出边）
            // 为了演示，我们这里只做前向搜索

            // 如果已经找到路径，提前退出
            if (meetingNode != -1 && iterations > 100) {
                break;
            }
        }

        // 重建路径
        if (meetingNode == -1) {
            return new SearchResult(Collections.emptyList(), Double.MAX_VALUE, iterations);
        }

        // 重建路径：前向 + 反向
        List<Integer> path = new ArrayList<>();

        // 从起点到相遇点
        List<Integer> forwardPath = new ArrayList<>();
        int node = meetingNode;
        while (node != startId) {
            forwardPath.add(node);
            node = forwardPrev.getOrDefault(node, startId);
        }
        forwardPath.add(startId);
        Collections.reverse(forwardPath);

        // 从相遇点到终点
        List<Integer> backwardPath = new ArrayList<>();
        node = meetingNode;
        while (node != endId && backwardPrev.containsKey(node)) {
            backwardPath.add(node);
            node = backwardPrev.get(node);
        }
        backwardPath.add(endId);

        path.addAll(forwardPath);
        // 避免重复相遇点
        for (int i = 1; i < backwardPath.size(); i++) {
            path.add(backwardPath.get(i));
        }

        return new SearchResult(path, bestDistance, iterations);
    }

    /**
     * 获取图中添加的所有捷径边
     */
    List<String> getShortcuts() {
        return shortcutsAdded;
    }

    /**
     * 获取预处理后的图
     */
    Graph getProcessedGraph() {
        return graph;
    }
}

// ============================================================
// 6. 搜索结果封装
// ============================================================

/**
 * 搜索算法的返回结果
 */
class SearchResult {
    List<Integer> path;      // 路径（节点 id 列表）
    double distance;         // 总距离
    int exploredNodes;       // 搜索过程中访问了多少节点（衡量效率）

    SearchResult(List<Integer> path, double distance, int exploredNodes) {
        this.path = path;
        this.distance = distance;
        this.exploredNodes = exploredNodes;
    }

    boolean hasPath() {
        return !path.isEmpty() && distance < Double.MAX_VALUE;
    }

    @Override
    public String toString() {
        if (!hasPath()) {
            return "❌ 未找到路径";
        }
        return "✅ 距离: " + String.format("%.2f", distance)
            + ", 路径节点数: " + path.size()
            + ", 探索节点数: " + exploredNodes;
    }
}

// ============================================================
// 7. 导航引擎：整合所有功能
// ============================================================

/**
 * 导航引擎，提供用户友好的接口
 *
 * 模拟高德地图导航的完整流程：
 * 1. 构建道路网络
 * 2. 选择算法（Dijkstra / A* / CH）
 * 3. 执行搜索
 * 4. 打印路线
 */
class NavigationEngine {
    private Graph graph;
    private Dijkstra dijkstra;
    private AStar astar;
    private ContractionHierarchies ch;

    NavigationEngine() {
        this.graph = new Graph();
    }

    /**
     * 构建一个模拟的道路网络
     *
     * 模拟北京到上海的部分路网，包含：
     * - 城市内部道路（低层级）
     * - 城际高速公路（高层级）
     * - 各种交叉口
     */
    void buildDemoNetwork() {
        System.out.println("===== 构建道路网络 =====");

        // 创建节点（模拟城市和关键路口）
        // 坐标是模拟的，只为了演示 A* 的启发式效果
        addNode(1, 0, 0, "北京");
        addNode(2, 20, 10, "天津");
        addNode(3, 50, 20, "济南");
        addNode(4, 80, 40, "南京");
        addNode(5, 100, 50, "上海");

        // 中间节点（模拟小路和县城）
        addNode(6, 10, 5, "廊坊");
        addNode(7, 35, 15, "沧州");
        addNode(8, 65, 30, "徐州");
        addNode(9, 90, 45, "苏州");

        // 添加道路（高速公路，层级 2）
        addBidirectional(1, 2, 12, "京沪高速(北京-天津)", 2);
        addBidirectional(2, 3, 30, "京沪高速(天津-济南)", 2);
        addBidirectional(3, 4, 35, "京沪高速(济南-南京)", 2);
        addBidirectional(4, 5, 25, "京沪高速(南京-上海)", 2);

        // 添加国道/省道（层级 1）
        addBidirectional(1, 6, 8, "京津公路", 1);
        addBidirectional(6, 7, 25, "国道 G105", 1);
        addBidirectional(7, 3, 20, "省道", 1);
        addBidirectional(3, 8, 28, "国道 G104", 1);
        addBidirectional(8, 4, 20, "省道", 1);
        addBidirectional(4, 9, 15, "宁沪公路", 1);
        addBidirectional(9, 5, 10, "沪苏公路", 1);

        // 添加小路（层级 0）
        addBidirectional(2, 6, 15, "县道", 0);
        addBidirectional(7, 2, 10, "乡道", 0);

        System.out.println("节点数: " + graph.nodeCount() + ", 边数: " + graph.edgeCount());
        System.out.println();

        // 初始化算法实例
        this.dijkstra = new Dijkstra(graph);
        this.astar = new AStar(graph);
    }

    /**
     * 执行 CH 预处理
     */
    void preprocessCH() {
        System.out.println();
        this.ch = new ContractionHierarchies(graph);
        ch.preprocess(1.0);
    }

    private void addNode(int id, double x, double y, String name) {
        graph.addNode(new Node(id, x, y, name));
    }

    private void addBidirectional(int a, int b, double weight, String name, int level) {
        graph.addBidirectionalEdge(a, b, weight, name, level);
    }

    /**
     * 执行导航，比较三种算法的效果
     */
    void navigate(int fromId, int toId) {
        Node from = graph.getNode(fromId);
        Node to = graph.getNode(toId);

        System.out.println("===== 导航: " + from.name + " → " + to.name + " =====");
        System.out.println();

        // 1. Dijkstra
        System.out.println("【Dijkstra 算法】");
        long start = System.nanoTime();
        SearchResult resultDijkstra = dijkstra.findShortestPath(fromId, toId);
        long end = System.nanoTime();
        printResult(resultDijkstra, from, to, (end - start) / 1_000_000.0);
        System.out.println();

        // 2. A*
        System.out.println("【A* 算法】");
        start = System.nanoTime();
        SearchResult resultAStar = astar.findShortestPath(fromId, toId);
        end = System.nanoTime();
        printResult(resultAStar, from, to, (end - start) / 1_000_000.0);
        System.out.println();

        // 3. CH（如果预处理过）
        if (ch != null) {
            System.out.println("【CH 快速查询】");
            start = System.nanoTime();
            SearchResult resultCH = ch.query(fromId, toId);
            end = System.nanoTime();
            printResult(resultCH, from, to, (end - start) / 1_000_000.0);
            System.out.println();
        }

        // 4. 对比总结
        System.out.println("===== 对比总结 =====");
        System.out.printf("%-15s %-12s %-12s %-12s%n", "算法", "距离", "探索节点", "时间(ms)");
        System.out.printf("%-15s %-12.2f %-12d %-12.2f%n",
            "Dijkstra", resultDijkstra.distance, resultDijkstra.exploredNodes, 0.0);
        System.out.printf("%-15s %-12.2f %-12d %-12.2f%n",
            "A*", resultAStar.distance, resultAStar.exploredNodes, 0.0);
        if (ch != null) {
            SearchResult resultCH = ch.query(fromId, toId);
            System.out.printf("%-15s %-12.2f %-12d %-12s%n",
                "CH", resultCH.distance, resultCH.exploredNodes, "极快(预处理)");
        }
        System.out.println();
    }

    /**
     * 打印导航结果
     */
    private void printResult(SearchResult result, Node from, Node to, double timeMs) {
        if (!result.hasPath()) {
            System.out.println("  ❌ 未找到路径");
            return;
        }

        System.out.println("  " + result);
        System.out.println("  耗时: " + String.format("%.3f", timeMs) + " ms");

        // 打印路径详情
        System.out.print("  路线: ");
        for (int i = 0; i < result.path.size(); i++) {
            Node node = graph.getNode(result.path.get(i));
            if (node != null) {
                System.out.print(node.name);
            }
            if (i < result.path.size() - 1) {
                System.out.print(" → ");
            }
        }
        System.out.println();
    }
}

// ============================================================
// 8. 主程序：演示
// ============================================================

/**
 * 主程序
 *
 * 演示导航算法的工作流程，并对比 Dijkstra、A* 和 CH 的效果。
 */
public class NavigationAlgorithm {

    public static void main(String[] args) {
        System.out.println("======================================");
        System.out.println("     导航算法演示：高德地图核心原理     ");
        System.out.println("======================================");
        System.out.println();

        // 创建导航引擎
        NavigationEngine engine = new NavigationEngine();
        engine.buildDemoNetwork();

        // 执行 CH 预处理
        engine.preprocessCH();

        System.out.println();

        // 导航：北京 → 上海
        engine.navigate(1, 5);

        System.out.println();

        // 额外演示：北京 → 南京
        engine.navigate(1, 4);

        System.out.println();

        // 额外演示：济南 → 上海
        engine.navigate(3, 5);

        System.out.println();
        System.out.println("===== 演示结束 =====");
        System.out.println("核心原理回顾：");
        System.out.println("  - Dijkstra：均匀扩散，一定能找到最短路径");
        System.out.println("  - A*：加启发式，朝目标方向搜索，更快");
        System.out.println("  - CH：预处理加捷径，查询极快（工业标准）");
        System.out.println("  - 高德地图 = CH 预处理 + A* 搜索 + 分层路网 + 实时路况");
    }
}