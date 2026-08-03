import java.security.*;
import java.util.BitSet;

public class BloomFilter {
    private final BitSet bits;
    private final int hashCount;
    private final int size;

    public BloomFilter(int expectedInsertions, double falsePositiveRate) {
        this.size = (int) Math.ceil(-expectedInsertions * Math.log(falsePositiveRate) / (Math.log(2) * Math.log(2)));
        this.hashCount = Math.max(1, (int) Math.ceil((size / (double) expectedInsertions) * Math.log(2)));
        this.bits = new BitSet(size);
        System.out.println("布隆过滤器初始化：");
        System.out.println("  位数组大小: " + size + " bits (" + (size / 8 / 1024) + " KB)");
        System.out.println("  哈希函数数: " + hashCount);
        System.out.println("  期望元素数: " + expectedInsertions);
        System.out.println("  期望误判率: " + (falsePositiveRate * 100) + "%");
    }

    public void add(String element) {
        int[] positions = hash(element);
        for (int pos : positions) bits.set(pos);
    }

    public boolean mightContain(String element) {
        int[] positions = hash(element);
        for (int pos : positions) if (!bits.get(pos)) return false;
        return true;
    }

    private int[] hash(String element) {
        int[] result = new int[hashCount];
        int[] hashValues = hashString(element);
        for (int i = 0; i < hashCount; i++) {
            int combined = hashValues[0] + i * hashValues[1];
            result[i] = Math.abs(combined) % size;
        }
        return result;
    }

    private int[] hashString(String element) {
        String reversed = new StringBuilder(element).reverse().toString();
        return new int[]{element.hashCode(), reversed.hashCode()};
    }

    public static void main(String[] args) {
        BloomFilter bf = new BloomFilter(10000, 0.01);
        String[] words = {"apple", "banana", "cherry", "date", "elderberry"};
        for (String w : words) bf.add(w);

        System.out.println("\n【查询已存在的单词】");
        for (String w : words) System.out.println("  " + w + ": " + (bf.mightContain(w) ? "存在" : "不存在"));

        System.out.println("\n【查询不存在的单词】");
        String[] notInSet = {"orange", "grape", "kiwi", "mango", "lemon"};
        for (String w : notInSet) System.out.println("  " + w + ": " + (bf.mightContain(w) ? "可能存在(误判)" : "一定不存在"));

        System.out.println("\n【大规模误判率测试】");
        int insertCount = 10000, testCount = 10000, falsePositives = 0;
        BloomFilter bigBf = new BloomFilter(insertCount, 0.01);
        for (int i = 0; i < insertCount; i++) bigBf.add("element-" + i);
        for (int i = 0; i < testCount; i++) if (bigBf.mightContain("not-in-set-" + i)) falsePositives++;

        System.out.println("  误判次数: " + falsePositives);
        System.out.println("  实际误判率: " + (falsePositives * 100.0 / testCount) + "%");
        System.out.println("  期望误判率: 1.0%");
    }
}
