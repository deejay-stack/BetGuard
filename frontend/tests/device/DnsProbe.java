import java.io.ByteArrayOutputStream;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.UnknownHostException;
import java.util.Arrays;

/** Device-only probe. No application rule/history mutation; DNS responses use the real VPN. */
public final class DnsProbe {
    public static void main(String[] args) throws Exception {
        if (args.length < 2 || args.length > 3) throw new IllegalArgumentException("hostname expected-rcode [system]");
        String host = args[0];
        int expected = Integer.parseInt(args[1]);
        if (args.length == 3 && args[2].equals("system")) {
            try {
                InetAddress[] addresses = InetAddress.getAllByName(host);
                if (expected == 3) throw new AssertionError("Blocked hostname resolved through the system resolver");
                System.out.println(host + " system-resolver=RESOLVED addresses=" + addresses.length);
            } catch (UnknownHostException error) {
                if (expected != 3) throw error;
                System.out.println(host + " system-resolver=BLOCKED (UnknownHostException)");
            }
            return;
        }
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        out.write(new byte[] {0x42, 0x47, 1, 0, 0, 1, 0, 0, 0, 0, 0, 0});
        for (String label : host.split("\\.")) {
            byte[] bytes = label.getBytes("US-ASCII");
            out.write(bytes.length); out.write(bytes);
        }
        out.write(new byte[] {0, 0, 1, 0, 1});
        byte[] query = out.toByteArray();
        try (DatagramSocket socket = new DatagramSocket()) {
            socket.setSoTimeout(10000);
            socket.connect(InetAddress.getByName("10.77.0.2"), 53);
            socket.send(new DatagramPacket(query, query.length));
            byte[] bytes = new byte[4096];
            DatagramPacket response = new DatagramPacket(bytes, bytes.length);
            socket.receive(response);
            if (response.getLength() < 12 || bytes[0] != 0x42 || bytes[1] != 0x47)
                throw new AssertionError("Invalid DNS transaction");
            int rcode = bytes[3] & 15;
            int answers = ((bytes[6] & 255) << 8) | (bytes[7] & 255);
            System.out.println(host + " rcode=" + rcode + " answers=" + answers);
            if (rcode != expected || (expected == 3 && answers != 0))
                throw new AssertionError("Unexpected DNS enforcement result: " + Arrays.toString(Arrays.copyOf(bytes, 12)));
        }
    }
}
