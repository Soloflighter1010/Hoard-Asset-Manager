// Issue #414: a product's package often carries its own copy of a shader or tool (lilToon, Poiyomi), which the project
// may have already, through the VCC (under Packages/) or in Assets/. Importing the package's copy over a newer one puts
// the older version back, and importing it beside the VCC's makes two of it: either way Unity and the tool's own
// scripts warn. A tool's copy says what it is in its own package.json (its name and version). When the project has that
// tool at the same version or a newer one, the package's copy is left out (PackageTrim) and the window says so. A tool
// the project doesn't have, or has an older version of, comes in with the product as before, through Unity's dialog.
// Plain C#, no Unity references.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;

namespace SoloFlighter.Hoard
{
    /// <summary>A tool a package carries a copy of, and the version the project has.</summary>
    public sealed class BundledTool
    {
        public string Id;            // the name it's published under ("jp.lilxyzw.liltoon")
        public string Name;          // as people know it ("lilToon")
        public string Version;       // the package's copy's version
        public string Folder;        // where the package puts it ("Assets/lilToon")
        public string ManifestGuid;  // the GUID of its package.json
        public List<string> Guids = new List<string>();   // what the package puts in Folder, and Folder itself
        public string InProject;     // the version this project has, or null for none
    }

    /// <summary>Which tools a package carries, and which of them to leave out of an import.</summary>
    public static class BundledTools
    {
        const string Manifest = "/package.json";

        /// <summary>The tools Hoard knows (hoard/known_tools.json), by the names they're published under. Only these
        /// are ever left out: a product's own files never are, even when the product is a package of its own.</summary>
        public static readonly Dictionary<string, string> Known = new Dictionary<string, string>(StringComparer.Ordinal)
        {
            { "jp.lilxyzw.liltoon", "lilToon" },
            { "com.poiyomi.toon", "Poiyomi Toon" },
            { "nadena.dev.modular-avatar", "Modular Avatar" },
            { "nadena.dev.ndmf", "NDMF" },
            { "com.vrcfury.vrcfury", "VRCFury" },
            { "com.anatawa12.avatar-optimizer", "Avatar Optimizer" },
            { "com.vrchat.base", "VRChat SDK - Base" },
            { "com.vrchat.avatars", "VRChat SDK - Avatars" },
        };

        /// <summary>The known tools a package carries: each package.json in it (manifests, by GUID, from
        /// UnityPackageReader.ReadAssetsAndManifests) that names one with a version, and what the package puts in its
        /// folder. assets: the package's GUIDs and project paths.</summary>
        public static List<BundledTool> Find(Dictionary<string, string> assets, Dictionary<string, byte[]> manifests)
        {
            var found = new List<BundledTool>();
            if (assets == null || manifests == null) return found;
            foreach (var m in manifests)
            {
                string path;
                if (!assets.TryGetValue(m.Key, out path)) continue;
                path = path.Replace('\\', '/');
                if (!path.EndsWith(Manifest, StringComparison.Ordinal)) continue;
                string folder = path.Substring(0, path.Length - Manifest.Length);
                // a tool's own folder ("Assets/lilToon", "Assets/Creator/Shaders/lilToon"), never Assets/ or Packages/ itself
                if (!(folder.StartsWith("Assets/", StringComparison.Ordinal) || folder.StartsWith("Packages/", StringComparison.Ordinal))) continue;
                if (folder.EndsWith("/", StringComparison.Ordinal) || folder.Split('/').Length < 2) continue;
                // a package is a file anyone could have made: a path that climbs out ("Assets/../x") is no tool's
                if (Array.Exists(folder.Split('/'), part => part.Length == 0 || part == "." || part == "..") || folder.IndexOf(':') >= 0) continue;
                string id, version;
                if (!ReadManifest(m.Value, out id, out version)) continue;
                string name;
                if (!Known.TryGetValue(id, out name) || Parse(version) == null) continue;
                var tool = new BundledTool { Id = id, Name = name, Version = version, Folder = folder, ManifestGuid = m.Key };
                foreach (var a in assets)
                {
                    string p = a.Value.Replace('\\', '/');
                    if (p == folder || p.StartsWith(folder + "/", StringComparison.Ordinal)) tool.Guids.Add(a.Key);
                }
                tool.Guids.Sort(StringComparer.Ordinal);
                found.Add(tool);
            }
            found.Sort((a, b) => string.CompareOrdinal(a.Folder, b.Folder));
            return found;
        }

        /// <summary>A package.json's name and version, as written. False for one that isn't JSON or has neither.</summary>
        public static bool ReadManifest(byte[] bytes, out string id, out string version)
        {
            id = version = null;
            if (bytes == null) return false;
            try
            {
                string text = new UTF8Encoding(false, true).GetString(bytes).TrimStart('﻿');
                var doc = Json.Parse(text);
                if (doc.Kind != JsonKind.Object) return false;
                id = doc.Str("name");
                version = doc.Str("version");
            }
            catch (Exception e) when (e is JsonException || e is ArgumentException) { return false; }
            return !string.IsNullOrEmpty(id) && !string.IsNullOrEmpty(version);
        }

        /// <summary>The tools to leave out: those the project has at the same version or a newer one. A version that
        /// can't be read either side leaves the tool in, for Unity's dialog, as before.</summary>
        public static List<BundledTool> LeftOut(List<BundledTool> found)
        {
            var left = new List<BundledTool>();
            foreach (var t in found)
            {
                int c;
                if (t.InProject != null && TryCompare(t.InProject, t.Version, out c) && c >= 0) left.Add(t);
            }
            return left;
        }

        /// <summary>The GUIDs of what's left out, each once.</summary>
        public static HashSet<string> GuidsOf(List<BundledTool> tools)
        {
            var all = new HashSet<string>(StringComparer.Ordinal);
            foreach (var t in tools) all.UnionWith(t.Guids);
            return all;
        }

        /// <summary>What the window says: "lilToon 1.7.3 in Rusk.unitypackage was left out: this project has
        /// 1.10.3.", one line for each.</summary>
        public static string Words(List<BundledTool> left, string package)
        {
            var lines = new List<string>();
            foreach (var t in left)
            {
                int c;
                bool same = TryCompare(t.InProject, t.Version, out c) && c == 0;
                lines.Add(t.Name + " " + t.Version + " in " + package + " was left out: this project has " +
                          (same ? "it already." : t.InProject + "."));
            }
            return string.Join("\n", lines.ToArray());
        }

        /// <summary>Of the project paths taking a product out would remove (ProjectShare.Removable), those that aren't in
        /// a known tool's own folder: one with the tool's package.json, as lilToon's Assets/lilToon has. A tool stays,
        /// as other things in the project may use it, and an import may have left the product's copy out for it.
        /// read gives a project file's bytes, or null; tools gets the name of each tool kept.</summary>
        public static List<string> WithoutTools(List<string> paths, Func<string, byte[]> read, List<string> tools)
        {
            var toolAt = new Dictionary<string, string>(StringComparer.Ordinal);   // folder -> the tool it is, or null
            Func<string, string> tool = folder =>
            {
                string name;
                if (toolAt.TryGetValue(folder, out name)) return name;
                string id, version;
                byte[] bytes = null;
                try { bytes = read(folder + Manifest); } catch (Exception) { /* unreadable: not taken for a tool's */ }
                name = bytes != null && ReadManifest(bytes, out id, out version) && Known.TryGetValue(id, out name) ? name : null;
                toolAt[folder] = name;
                return name;
            };
            var left = new List<string>();
            foreach (string path in paths)
            {
                string found = tool(path);   // (a folder of its own: a tool's, when its package.json is in it)
                for (int i = path.LastIndexOf('/'); found == null && i > "Assets".Length; i = path.LastIndexOf('/', i - 1))
                    found = tool(path.Substring(0, i));
                if (found == null) left.Add(path);
                else if (!tools.Contains(found)) tools.Add(found);
            }
            return left;
        }

        /// <summary>Compare two versions as Unity's packages write them (semver: "1.10.3", "2.0.0-beta.2"): part by
        /// part as numbers, a pre-release before its release. False when either can't be read.</summary>
        public static bool TryCompare(string a, string b, out int result)
        {
            result = 0;
            var x = Parse(a);
            var y = Parse(b);
            if (x == null || y == null) return false;
            for (int i = 0; i < Math.Max(x.Core.Length, y.Core.Length); i++)
            {
                long p = i < x.Core.Length ? x.Core[i] : 0, q = i < y.Core.Length ? y.Core[i] : 0;
                if (p != q) { result = p < q ? -1 : 1; return true; }
            }
            if (x.Pre.Length == 0 || y.Pre.Length == 0)
            {
                result = x.Pre.Length == y.Pre.Length ? 0 : x.Pre.Length == 0 ? 1 : -1;   // a release after its pre-releases
                return true;
            }
            for (int i = 0; i < Math.Min(x.Pre.Length, y.Pre.Length); i++)
            {
                int c = ComparePre(x.Pre[i], y.Pre[i]);
                if (c != 0) { result = c; return true; }
            }
            result = x.Pre.Length.CompareTo(y.Pre.Length);
            return true;
        }

        /// <summary>A version's numbers and its pre-release parts.</summary>
        sealed class Parsed { public long[] Core; public string[] Pre; }

        /// <summary>"v1.10.3-beta.2+build" as {1, 10, 3} and {"beta", "2"}; null when it isn't a version.</summary>
        static Parsed Parse(string v)
        {
            if (string.IsNullOrEmpty(v) || v.Length > 64) return null;
            v = v.Trim();
            if (v.StartsWith("v", StringComparison.OrdinalIgnoreCase)) v = v.Substring(1);
            int plus = v.IndexOf('+');
            if (plus >= 0) v = v.Substring(0, plus);   // build metadata: never part of the order
            int dash = v.IndexOf('-');
            string core = dash < 0 ? v : v.Substring(0, dash), pre = dash < 0 ? "" : v.Substring(dash + 1);
            string[] parts = core.Split('.');
            if (parts.Length == 0 || parts.Length > 4) return null;
            var nums = new long[parts.Length];
            for (int i = 0; i < parts.Length; i++)
                if (parts[i].Length == 0 || parts[i].Length > 9 || !long.TryParse(parts[i], NumberStyles.None, CultureInfo.InvariantCulture, out nums[i])) return null;
            string[] pres = pre.Length == 0 ? new string[0] : pre.Split('.');
            foreach (string p in pres) if (p.Length == 0) return null;
            if (dash >= 0 && pres.Length == 0) return null;
            return new Parsed { Core = nums, Pre = pres };
        }

        /// <summary>Two pre-release parts: numbers as numbers, before words; words in ASCII order.</summary>
        static int ComparePre(string a, string b)
        {
            long p = 0, q = 0;
            bool an = a.Length <= 9 && long.TryParse(a, NumberStyles.None, CultureInfo.InvariantCulture, out p);
            bool bn = b.Length <= 9 && long.TryParse(b, NumberStyles.None, CultureInfo.InvariantCulture, out q);
            if (an && bn) return p.CompareTo(q);
            if (an != bn) return an ? -1 : 1;
            return Math.Sign(string.CompareOrdinal(a, b));
        }
    }
}
