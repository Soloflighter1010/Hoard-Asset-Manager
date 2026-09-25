// Hoard's catalog.json: every asset Hoard has downloaded, checked against the promises in Hoard's
// docs/DATA-FORMATS.md before anything is shown or opened. Plain C#, no Unity references.
using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using System.Text.RegularExpressions;

namespace SoloFlighter.Hoard
{
    public sealed class HoardAsset
    {
        public string Store, Name, Creator, Folder, Url, Variants, Added;
        public List<string> Files = new List<string>();
        public List<string> Tags = new List<string>();
        public List<string> SuggestedTags = new List<string>();
        public string Key { get { return Store + "/" + Folder; } }

        // Worked out once when the catalog is loaded (in the background), so the window never touches the disk
        // to draw a row: the .unitypackage files that are really there, the picture, and what search looks in.
        public List<string> PackagePaths = new List<string>();
        public string ThumbPath;
        public string SearchText = "";
        public bool HasPackages;
    }

    public sealed class HoardCatalog
    {
        public const int NewestVersion = 3;
        const long MaxBytes = 64L * 1024 * 1024;
        static readonly string[] Stores = { "Booth", "Gumroad", "Jinxxy", "Payhip", "Itch" };
        static readonly Dictionary<string, string> StoreSites = new Dictionary<string, string>
        {
            { "Booth", "booth.pm" }, { "Gumroad", "gumroad.com" }, { "Jinxxy", "jinxxy.com" }, { "Payhip", "payhip.com" },
            { "Itch", "itch.io" },
        };

        /// <summary>A store as people write it, from the name of its folder ("Itch" is itch.io).</summary>
        public static string StoreLabel(string store)
        {
            return store == "Itch" ? "itch.io" : store;
        }
        static readonly Regex BadPathChars = new Regex("[<>:\"\\\\|?*]");

        public string Root;
        public List<HoardAsset> Assets = new List<HoardAsset>();
        public SealState SealStatus = SealState.Unsealed;
        public string Problem;          // why the catalog couldn't be read at all, or null
        public int LeftOut;             // entries that broke a promise, and were left out

        public static HoardCatalog Load(string root, byte[] key)
        {
            return Load(root, key == null ? new List<byte[]>() : new List<byte[]> { key });
        }

        /// <summary>Read catalog.json from Hoard's downloads folder, checking its seal with whichever of these keys
        /// (this account's Hoard keys) it names, and work out each product's files and picture. Never throws:
        /// problems are in Problem. Meant to run in the background: it's the only part that reads the disk.</summary>
        public static HoardCatalog Load(string root, IList<byte[]> keys)
        {
            var cat = new HoardCatalog { Root = Path.GetFullPath(root) };
            string file = Path.Combine(cat.Root, "catalog.json");
            try
            {
                if (!File.Exists(file)) { cat.Problem = "No catalog yet. Download something with Hoard first."; return cat; }
                if (new FileInfo(file).Length > MaxBytes) { cat.Problem = "catalog.json is too large to be Hoard's."; return cat; }
                var doc = Json.Parse(File.ReadAllText(file, Encoding.UTF8));
                if (doc.Kind != JsonKind.Object || doc.Str("format") != "hoard-catalog")
                { cat.Problem = "catalog.json isn't a Hoard catalog."; return cat; }
                long version = doc.Long("version") ?? 0;
                if (version < 2) { cat.Problem = "catalog.json is from an old Hoard. Sync in Hoard to update it."; return cat; }
                if (version > NewestVersion) { cat.Problem = "catalog.json is from a newer Hoard. Update this package in VCC."; return cat; }
                cat.SealStatus = Seal.Check(doc, keys);
                var assets = doc.Get("assets");
                if (assets == null || assets.Kind != JsonKind.Array) { cat.Problem = "catalog.json has no asset list."; return cat; }
                foreach (var entry in assets.Items)
                {
                    var asset = Read(entry, cat.SealStatus != SealState.Changed);
                    if (asset != null) cat.Assets.Add(asset); else cat.LeftOut++;
                }
                cat.Resolve();
            }
            catch (JsonException e) { cat.Problem = "catalog.json couldn't be read (" + e.Message + ")."; }
            catch (Exception e) { cat.Problem = "catalog.json couldn't be read (" + e.GetType().Name + ")."; }
            return cat;
        }

        static HoardAsset Read(JsonValue e, bool trustLinks)
        {
            if (e == null || e.Kind != JsonKind.Object) return null;
            var a = new HoardAsset
            {
                Store = e.Str("store"), Name = e.Str("name"), Creator = e.Str("creator"), Folder = e.Str("folder"),
                Url = e.Str("url"), Variants = e.Str("variants"), Added = e.Str("added"),
                Files = e.Strings("files"), Tags = e.Strings("tags"), SuggestedTags = e.Strings("suggested_tags"),
            };
            if (Array.IndexOf(Stores, a.Store) < 0 || !CleanText(a.Name, 300) || !CleanText(a.Creator, 200)) return null;
            if (a.Variants != null && !CleanText(a.Variants, 300)) return null;
            if (!PlainPath(a.Folder)) return null;
            a.Files = a.Files.FindAll(PlainPath);
            a.Tags = a.Tags.FindAll(t => CleanText(t, 40));
            a.SuggestedTags = a.SuggestedTags.FindAll(t => CleanText(t, 40));
            if (!trustLinks || !StoreLink(a.Store, a.Url)) a.Url = null;
            return a;
        }

        /// <summary>No control or invisible formatting characters, not empty, not too long.</summary>
        public static bool CleanText(string s, int max)
        {
            if (string.IsNullOrEmpty(s) || s.Length > max) return false;
            foreach (char c in s)
            {
                var cat = char.GetUnicodeCategory(c);
                if (char.IsControl(c) || cat == System.Globalization.UnicodeCategory.Format) return false;
            }
            return true;
        }

        /// <summary>A plain relative path: "/" between parts, no "..", ".", empty parts, drive letters or odd characters.</summary>
        public static bool PlainPath(string p)
        {
            if (string.IsNullOrEmpty(p) || p.Length > 1000 || p.StartsWith("/") || BadPathChars.IsMatch(p) || !CleanText(p, 1000))
                return false;
            foreach (string part in p.Split('/'))
                if (part.Length == 0 || part == "." || part == "..") return false;
            return true;
        }

        /// <summary>An https address on the asset's own store (or a subdomain), with no user name or port.</summary>
        public static bool StoreLink(string store, string url)
        {
            Uri u;
            if (string.IsNullOrEmpty(url) || !StoreSites.ContainsKey(store ?? "") || !Uri.TryCreate(url, UriKind.Absolute, out u)) return false;
            if (u.Scheme != "https" || !string.IsNullOrEmpty(u.UserInfo) || !u.IsDefaultPort) return false;
            string host = u.Host.ToLowerInvariant().TrimEnd('.'), site = StoreSites[store];
            return host == site || host.EndsWith("." + site);
        }

        /// <summary>The full path of one of an asset's files, only if it's a plain file inside the downloads folder,
        /// reached without going through any link or junction. Null otherwise.</summary>
        /// <summary>Work out each product's files, picture and search text (see HoardAsset).</summary>
        public void Resolve()
        {
            foreach (var a in Assets)
            {
                a.HasPackages = a.Files.Exists(IsUnityPackage);
                a.PackagePaths = new List<string>();
                foreach (string f in a.Files)
                {
                    if (!IsUnityPackage(f)) continue;
                    string p = FilePath(a, f);
                    if (p != null) a.PackagePaths.Add(p);
                }
                a.ThumbPath = Thumbnail(a);
                a.SearchText = (a.Name + " " + a.Creator + " " + string.Join(" ", a.Tags)).ToLowerInvariant();
            }
        }

        public static bool IsUnityPackage(string file) { return file.EndsWith(".unitypackage", StringComparison.OrdinalIgnoreCase); }

        public string FilePath(HoardAsset a, string file)
        {
            if (!PlainPath(a.Folder) || !PlainPath(file)) return null;
            return Inside(a.Folder + "/" + file, false);
        }

        /// <summary>The asset's picture (_thumbnail.png or .jpg: the kinds Unity can show), or null.</summary>
        public string Thumbnail(HoardAsset a)
        {
            foreach (string ext in new[] { ".png", ".jpg", ".jpeg" })
            {
                string p = Inside(a.Folder + "/_thumbnail" + ext, false);
                if (p != null) return p;
            }
            return null;
        }

        public string FolderPath(HoardAsset a) { return PlainPath(a.Folder) ? Inside(a.Folder, true) : null; }

        // Folders already checked (a real folder, not a link or junction): many products share a store and creator
        // folder, so each is looked at once, not once per product. Only used by one thread at a time.
        readonly Dictionary<string, bool> folderOk = new Dictionary<string, bool>(StringComparer.Ordinal);
        public int DiskChecks;   // how many times the disk was asked, for tests

        bool RealFolder(string path)
        {
            bool ok;
            if (folderOk.TryGetValue(path, out ok)) return ok;
            DiskChecks++;
            ok = Directory.Exists(path) && (File.GetAttributes(path) & FileAttributes.ReparsePoint) == 0;   // links and junctions
            folderOk[path] = ok;
            return ok;
        }

        string Inside(string rel, bool folder)
        {
            string root = Root.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
            string path = root;
            string[] parts = rel.Split('/');
            for (int n = 0; n < parts.Length; n++)
            {
                path = Path.Combine(path, parts[n]);
                bool last = n == parts.Length - 1;
                if (!last || folder)
                {
                    if (!RealFolder(path)) return null;
                    continue;
                }
                DiskChecks++;
                if (!File.Exists(path) || (File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0) return null;
            }
            string full = Path.GetFullPath(path);
            return full.StartsWith(root + Path.DirectorySeparatorChar, StringComparison.Ordinal) ? full : null;
        }
    }
}
