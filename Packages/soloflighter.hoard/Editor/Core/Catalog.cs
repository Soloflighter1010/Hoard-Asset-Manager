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
        public string Location;   // a Local item listed where it is (Hoard's issue #80): its own folder; else null
        public string Note;       // a Local item: who or what it's for
        public string Library;    // a product in another of Hoard's library folders (on another drive): that folder; else null
        public List<string> Files = new List<string>();
        public List<string> Tags = new List<string>();
        public List<string> SuggestedTags = new List<string>();
        public List<HoardNeed> Needs = new List<HoardNeed>();   // what its packages use from elsewhere (Hoard 4.0)
        public string Key { get { return Store + "/" + Folder; } }

        // Worked out once when the catalog is loaded (in the background), so the window never touches the disk
        // to draw a row: the .unitypackage files that are really there (those in its .zip files too: PackageFile), the
        // picture, and what search looks in.
        public List<string> PackagePaths = new List<string>();
        public string ThumbPath;
        public string SearchText = "";
        public bool HasPackages;
    }

    /// <summary>Something a product's packages use that isn't in them (Hoard's What it needs): a tool, such as a
    /// shader, or another product Hoard has downloaded. It's in a project when every one of its GUIDs is.</summary>
    public sealed class HoardNeed
    {
        public string Kind, Name, Url, Creator, Store, Folder;   // Kind: "tool" or "product"
        public List<string> Versions = new List<string>();
        public List<string> Guids = new List<string>();
        public string Label { get { return Versions.Count > 0 ? Name + " " + string.Join(", ", Versions.ToArray()) : Name; } }
    }

    public sealed class HoardCatalog
    {
        public const int NewestVersion = 4;
        const long MaxBytes = 64L * 1024 * 1024;
        public static readonly string[] Stores = { "Booth", "Gumroad", "Jinxxy", "Payhip", "Itch", "Local" };   // by their folders' names
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
        static readonly Regex Guid32 = new Regex("^[0-9a-f]{32}$");
        static readonly Regex ToolVersion = new Regex("^[0-9]{1,3}\\.[0-9]{1,3}$");
        // the tools' own websites (Hoard's known_tools.json): a need's "Get it" link goes nowhere else
        static readonly string[] ToolSites = { "lilxyzw.github.io", "www.poiyomi.com", "modular-avatar.nadena.dev", "vrcfury.com",
                                               "ndmf.nadena.dev", "vpm.anatawa12.com", "creators.vrchat.com" };

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
                    var asset = Read(entry, cat.SealStatus != SealState.Changed, cat.SealStatus == SealState.Sealed);
                    if (asset != null) cat.Assets.Add(asset); else cat.LeftOut++;
                }
                cat.Resolve();
            }
            catch (JsonException e) { cat.Problem = "catalog.json couldn't be read (" + e.Message + ")."; }
            catch (Exception e) { cat.Problem = "catalog.json couldn't be read (" + e.GetType().Name + ")."; }
            return cat;
        }

        /// <summary>One catalog entry, or null when it breaks a promise. trustPlaces: the catalog was sealed by Hoard on
        /// this computer, so a Local item's own folder, or another library folder (both outside the downloads
        /// folder), can be believed; otherwise such an item is left out, as it can't be found.</summary>
        static HoardAsset Read(JsonValue e, bool trustLinks, bool trustPlaces)
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
            string location = e.Str("location");
            if (location != null)
            {
                if (a.Store != "Local" || !trustPlaces || !PlainLocation(location)) return null;
                a.Location = location;
            }
            string library = e.Str("library");   // version 4: a product in another library folder
            if (library != null)
            {
                if (location != null || !trustPlaces || !PlainLocation(library)) return null;
                a.Library = library;
            }
            string note = e.Str("note");
            a.Note = a.Store == "Local" && note != null && CleanText(note, 300) ? note : null;
            var needs = e.Get("needs");
            if (needs != null && needs.Kind == JsonKind.Array)
                foreach (var n in needs.Items)
                {
                    if (a.Needs.Count >= 30) break;
                    var need = ReadNeed(n, trustLinks);
                    if (need != null) a.Needs.Add(need);
                }
            return a;
        }

        /// <summary>One of a product's needs, or null when it breaks a promise (left out, not the product).</summary>
        static HoardNeed ReadNeed(JsonValue n, bool trustLinks)
        {
            if (n == null || n.Kind != JsonKind.Object) return null;
            var need = new HoardNeed { Kind = n.Str("kind"), Name = n.Str("name"), Guids = n.Strings("guids") };
            if ((need.Kind != "tool" && need.Kind != "product") || !CleanText(need.Name, 200)) return null;
            if (need.Guids.Count == 0 || need.Guids.Count > 50 || !need.Guids.TrueForAll(g => Guid32.IsMatch(g))) return null;
            if (need.Kind == "tool")
            {
                need.Versions = n.Strings("versions");
                if (need.Versions.Count > 30 || !need.Versions.TrueForAll(v => ToolVersion.IsMatch(v))) return null;
                string url = n.Str("url");
                need.Url = trustLinks && ToolLink(url) ? url : null;
            }
            else
            {
                need.Creator = n.Str("creator"); need.Store = n.Str("store"); need.Folder = n.Str("folder");
                if (!CleanText(need.Creator, 200) || Array.IndexOf(Stores, need.Store) < 0 || !PlainPath(need.Folder)) return null;
            }
            return need;
        }

        /// <summary>An https address on one of the tools' own websites, with no user name or port.</summary>
        public static bool ToolLink(string url)
        {
            Uri u;
            if (string.IsNullOrEmpty(url) || !Uri.TryCreate(url, UriKind.Absolute, out u)) return false;
            return u.Scheme == "https" && string.IsNullOrEmpty(u.UserInfo) && u.IsDefaultPort
                   && Array.IndexOf(ToolSites, u.Host.ToLowerInvariant()) >= 0;
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

        /// <summary>A Local item's own folder: a full path, written as the system writes it, with nothing odd in it.</summary>
        public static bool PlainLocation(string p)
        {
            if (!CleanText(p, 1000) || !Path.IsPathRooted(p)) return false;
            try { return Path.GetFullPath(p) == p; }
            catch (Exception) { return false; }
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

        /// <summary>Work out each product's files, picture and search text (see HoardAsset).</summary>
        public void Resolve()
        {
            foreach (var a in Assets)
            {
                a.PackagePaths = new List<string>();
                foreach (string f in a.Files)
                {
                    bool zip = f.EndsWith(".zip", StringComparison.OrdinalIgnoreCase);
                    if (!IsUnityPackage(f) && !zip) continue;
                    string p = FilePath(a, f);
                    if (p == null) continue;
                    if (zip) a.PackagePaths.AddRange(PackageFile.PackagesIn(p));   // the packages it came zipped in
                    else a.PackagePaths.Add(p);
                }
                a.HasPackages = a.Files.Exists(IsUnityPackage) || a.PackagePaths.Count > 0;
                a.ThumbPath = Thumbnail(a);
                a.SearchText = (a.Name + " " + a.Creator + " " + string.Join(" ", a.Tags)).ToLowerInvariant();
            }
        }

        public static bool IsUnityPackage(string file) { return file.EndsWith(".unitypackage", StringComparison.OrdinalIgnoreCase); }

        /// <summary>The full path of one of an asset's files, only if it's a plain file inside the downloads folder,
        /// reached without going through any link or junction. Null otherwise.</summary>
        public string FilePath(HoardAsset a, string file)
        {
            return PlainPath(file) ? Under(a, file, false) : null;
        }

        /// <summary>A file (or with file null, the folder) of an asset: inside the downloads folder (or the other library
        /// folder it's in), or for a Local item listed where it is, inside its own folder. Never through a link or
        /// junction.</summary>
        string Under(HoardAsset a, string file, bool folder)
        {
            if (a.Location != null)
            {
                if (!RealFolder(a.Location)) return null;
                return file == null ? Path.GetFullPath(a.Location) : Inside(a.Location, file, folder);
            }
            if (!PlainPath(a.Folder)) return null;
            string top = a.Library ?? Root;   // the library folder it's in: the downloads folder, or one on another drive
            if (a.Library != null && !RealFolder(a.Library)) return null;
            return file == null ? Inside(top, a.Folder, true) : Inside(top, a.Folder + "/" + file, folder);
        }

        /// <summary>Pictures the window can show: PNG and JPEG (Unity's own), and GIF, animated ones included
        /// (GifDecoder). Not WebP or AVIF, which Hoard can save as a store's picture.</summary>
        public static readonly string[] PictureTypes = { ".png", ".jpg", ".jpeg", ".gif" };
        static readonly Regex PreviewHint = new Regex("preview|thumb|cover|icon|promo|banner", RegexOptions.IgnoreCase);

        public static bool IsPicture(string file)
        {
            foreach (string ext in PictureTypes) if (file.EndsWith(ext, StringComparison.OrdinalIgnoreCase)) return true;
            return false;
        }

        /// <summary>The asset's picture, as Hoard's own pages choose it: the _thumbnail Hoard saved, else one of its
        /// files that looks like a preview, else any picture among them. Only kinds the window can show; null when
        /// there's none.</summary>
        public string Thumbnail(HoardAsset a)
        {
            foreach (string ext in PictureTypes)
            {
                string p = Under(a, "_thumbnail" + ext, false);
                if (p != null) return p;
            }
            var pictures = a.Files.FindAll(IsPicture);
            foreach (string f in pictures)
                if (PreviewHint.IsMatch(Path.GetFileNameWithoutExtension(f)))
                {
                    string p = FilePath(a, f);
                    if (p != null) return p;
                }
            foreach (string f in pictures)
            {
                string p = FilePath(a, f);
                if (p != null) return p;
            }
            return null;
        }

        public string FolderPath(HoardAsset a) { return Under(a, null, true); }

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

        string Inside(string baseFolder, string rel, bool folder)
        {
            // a library folder that's a whole drive ("E:\", or "/") keeps its separator: "E:" alone is the current
            // folder on that drive, and Path.Combine("E:", "Booth") is "E:Booth"
            string root = baseFolder.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
            string drive = Path.GetPathRoot(baseFolder) ?? "";
            if (root.Length < drive.Length) root = drive;
            string prefix = root.EndsWith(Path.DirectorySeparatorChar.ToString(), StringComparison.Ordinal)
                            || root.EndsWith(Path.AltDirectorySeparatorChar.ToString(), StringComparison.Ordinal)
                ? root : root + Path.DirectorySeparatorChar;
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
            return full.StartsWith(prefix, StringComparison.Ordinal) ? full : null;
        }
    }
}
