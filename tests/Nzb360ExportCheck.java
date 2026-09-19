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
                    check(Boolean.FALSE.equals(prefs.get(prefix + "_localconnectionswitch_preference")));
                }
                check(prefs.get("nzbdrone_apikey_preference").equals("TEST-API-KEY"));
                check(prefs.get("radarr_apikey_preference").equals("TEST-API-KEY"));
                check(read(zip, "nzb360prefs.xml").equals(Map.of("version", "24.4.1")));
                check(read(zip, "servers.xml").isEmpty());
            }
        }
        // SABnzbd keys from the 24.4.1 sample; its enable flag is the generic one.
        try (ZipFile zip = new ZipFile(new File(args[0], "local-sab.zip"))) {
            Map<?, ?> prefs = read(zip, "com.kevinforeman.nzb360_preferences.xml");
            check(Boolean.TRUE.equals(prefs.get("server_enabled_preference")));
            check(prefs.get("sabnzbd_server_primary_connectionstring_preference").equals("http://192.0.2.5:8085"));
            check(prefs.get("sabnzbd_server_local_connectionstring_preference").equals(""));
            check(prefs.get("sabapi_preference").equals("TEST-SAB-KEY"));
        }
        // One file for home and away.
        try (ZipFile zip = new ZipFile(new File(args[0], "both.zip"))) {
            Map<?, ?> prefs = read(zip, "com.kevinforeman.nzb360_preferences.xml");
            for (String prefix : List.of("nzbdrone", "radarr", "torrent")) {
                check(((String)prefs.get(prefix + "_server_primary_connectionstring_preference")).startsWith("https://"));
                check(((String)prefs.get(prefix + "_server_local_connectionstring_preference")).startsWith("http://192.0.2.5:"));
                check(prefs.get(prefix + "_server_SSID_preference").equals("Maison"));
                check(Boolean.TRUE.equals(prefs.get(prefix + "_localconnectionswitch_preference")));
            }
            check(Boolean.FALSE.equals(prefs.get("server_enabled_preference")));
            check(!prefs.containsKey("sabapi_preference"));
        }
        // Lidarr, Seerr (overseerr_ keys) and Transmission (torrent slot), keys
        // read from a 24.4.1 backup made after configuring them.
        try (ZipFile zip = new ZipFile(new File(args[0], "local-extra.zip"))) {
            Map<?, ?> prefs = read(zip, "com.kevinforeman.nzb360_preferences.xml");
            for (String prefix : List.of("lidarr", "overseerr", "torrent")) {
                check(Boolean.TRUE.equals(prefs.get(prefix + "_server_enabled_preference")));
                check(((String)prefs.get(prefix + "_server_primary_connectionstring_preference")).startsWith("http://192.0.2.5:"));
                check(Boolean.FALSE.equals(prefs.get(prefix + "_localconnectionswitch_preference")));
            }
            check(prefs.get("lidarr_apikey_preference").equals("TEST-LIDARR-KEY"));
            check(prefs.get("overseerr_apikey_preference").equals("TEST-SEERR-KEY"));
            check(prefs.get("torrent_client_preference").equals("transmission"));
            check(prefs.get("torrent_username").equals("tr-user"));
            check(prefs.get("torrent_password").equals("TR-PASS"));
            check(prefs.get("torrent_rpc_path").equals(""));
        }
        try (ZipFile zip = new ZipFile(new File(args[0], "qb-first.zip"))) {
            Map<?, ?> prefs = read(zip, "com.kevinforeman.nzb360_preferences.xml");
            check(prefs.get("torrent_client_preference").equals("qbittorrent"));
            check(prefs.get("torrent_username").equals("test-user"));
        }
        System.out.println("JVM: all three ZIP entries deserialize correctly; credentials, booleans, Unicode, network mapping, SABnzbd, Lidarr, Seerr, Transmission and Wi-Fi switch OK");
    }
}
