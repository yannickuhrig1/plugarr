// Independent JVM reader for synthetic PlugArr output only, never user backups.
import java.io.*;
import java.util.*;
import java.util.zip.*;

class Nzb360ExportCheck {
    static void check(boolean condition) { if (!condition) throw new AssertionError("Export validation failed"); }
    static Map<?, ?> read(ZipFile zip, String name) throws Exception {
        try (ObjectInputStream in = new ObjectInputStream(zip.getInputStream(zip.getEntry(name)))) {
            in.setObjectInputFilter(info -> {
                if (info.depth() > 10 || info.references() > 1000 || info.streamBytes() > 100000) return ObjectInputFilter.Status.REJECTED;
                Class<?> c = info.serialClass();
                if (c == null || c == HashMap.class || c == Boolean.class || c == String.class || c == Map.Entry[].class) return ObjectInputFilter.Status.ALLOWED;
                return ObjectInputFilter.Status.REJECTED;
            });
            Map<?, ?> result = (Map<?, ?>) in.readObject();
            check(in.read() == -1);
            return result;
        }
    }
    public static void main(String[] args) throws Exception {
        for (String mode : List.of("local", "remote")) {
            try (ZipFile zip = new ZipFile(new File(args[0], mode + ".zip"))) {
                check(zip.size() == 3);
                Map<?, ?> prefs = read(zip, "com.kevinforeman.nzb360_preferences.xml");
                check(prefs.get("version").equals("24.4.1"));
                check(prefs.get("torrent_client_preference").equals("qbittorrent"));
                check(prefs.get("torrent_password").equals("TEST-é\u0000😀-password"));
                check(prefs.get("torrent_username").equals("test-user"));
                for (String prefix : List.of("nzbdrone", "radarr", "torrent")) {
                    check(Boolean.TRUE.equals(prefs.get(prefix + "_server_enabled_preference")));
                    check(((String)prefs.get(prefix + "_server_primary_connectionstring_preference")).startsWith(mode.equals("remote") ? "https://" : "http://192.0.2.5:"));
                    check(prefs.get(prefix + "_server_local_connectionstring_preference").equals(""));
                }
                check(prefs.get("nzbdrone_apikey_preference").equals("TEST-API-KEY"));
                check(prefs.get("radarr_apikey_preference").equals("TEST-API-KEY"));
                check(read(zip, "nzb360prefs.xml").equals(Map.of("version", "24.4.1")));
                check(read(zip, "servers.xml").isEmpty());
            }
        }
        System.out.println("JVM: all three ZIP entries deserialize correctly; credentials, booleans, Unicode and network mapping OK");
    }
}
