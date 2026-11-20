// Issue #414: before a package goes to Unity's import dialog, a tool it carries a copy of (lilToon, Poiyomi) that this
// project has already, at the same version or a newer one, is left out of it (BundledTools, PackageTrim): importing the
// older copy over the project's, or beside the VCC's under Packages/, made Unity and the tool warn. What was left out
// is said in the Console and in the Hoard window, which keeps it (in SessionState) until the next import.
using System;
using System.Collections.Generic;
using System.IO;
using UnityEditor;

namespace SoloFlighter.Hoard.Editor
{
    /// <summary>A package ready for Unity's import dialog, without the tools this project has already.</summary>
    public static class Bundled
    {
        const string SaidKey = "SoloFlighter.Hoard.LeftOut";

        /// <summary>What the last imports left out, for the window to say; null when they left out nothing.</summary>
        public static string Said { get { string s = SessionState.GetString(SaidKey, ""); return s.Length == 0 ? null : s; } }

        /// <summary>The window's note was read: it goes.</summary>
        public static void Forget() { SessionState.EraseString(SaidKey); }

        /// <summary>What Prepare found: import the package as it is, import the copy without the tools, or don't
        /// import it (cancelled).</summary>
        public enum Outcome { AsItIs, Trimmed, Cancelled }

        /// <summary>Before a package (a file, or one in a .zip) goes to Unity's dialog: a copy of it without the tools
        /// this project has at the same version or a newer one, in Library/Hoard/Trimmed (made straight from the .zip,
        /// for one in a zip), when it carries any. A package Hoard's index read and found no package.json in isn't read
        /// again. Reading and copying show how far they've got and can be cancelled. add: one of a set's packages, so
        /// what it leaves out is said with what the others did.</summary>
        public static Outcome Prepare(string package, bool add, out string trimmed)
        {
            trimmed = null;
            if (!add) Forget();
            if (PackageIndex.CarriesManifest(package) == false) return Outcome.AsItIs;   // no package.json: no tool in it
            string name = PackageFile.Name(package);
            List<BundledTool> left;
            try
            {
                Dictionary<string, byte[]> manifests;
                HashSet<string> files;
                var assets = UnityPackageReader.ReadAssetsAndManifests(package, out manifests, out files,
                    f => EditorUtility.DisplayCancelableProgressBar("Hoard", "Looking at what's in " + name, (float)f));
                bool any = false;
                foreach (string p in assets.Values) if (p.Replace('\\', '/').EndsWith("/package.json", StringComparison.Ordinal)) any = true;
                PackageIndex.Remember(package, any);   // (the next import of it needn't read it, when there's none)
                var found = BundledTools.Find(assets, manifests);
                if (found.Count == 0) return Outcome.AsItIs;
                foreach (var tool in found) tool.InProject = ProjectVersion(tool);
                left = BundledTools.LeftOut(found);
                if (left.Count == 0) return Outcome.AsItIs;
                foreach (var tool in left) BundledTools.Divide(tool, assets, files, g => !string.IsNullOrEmpty(AssetDatabase.GUIDToAssetPath(g)));
            }
            catch (OperationCanceledException) { return Outcome.Cancelled; }
            catch (Exception e)   // not a package Hoard can read: Unity's dialog offers it as it is, and says what's wrong
            {
                UnityEngine.Debug.LogWarning("Hoard: couldn't look at the tools " + name + " carries (" + e.Message + "), so all of it is offered.");
                return Outcome.AsItIs;
            }
            finally { EditorUtility.ClearProgressBar(); }
            try
            {
                trimmed = PackageTrim.Without(package, BundledTools.GuidsOf(left), Path.Combine("Library", "Hoard", "Trimmed"),
                    f => EditorUtility.DisplayCancelableProgressBar("Hoard", "Leaving out what this project has already", (float)f));
            }
            catch (OperationCanceledException) { return Outcome.Cancelled; }
            catch (Exception e)
            {
                // the copy couldn't be made (a full disk, a locked file): importing it all would put the older tool over
                // the project's, which is what this is for, so that's asked first
                EditorUtility.ClearProgressBar();
                var older = left.ConvertAll(t => t.Name + " " + t.Version + " (this project has " + t.InProject + ")");
                return EditorUtility.DisplayDialog("Hoard", "Hoard couldn't make a copy of " + name + " without " + string.Join(", ", older.ToArray()) +
                        ": " + e.Message + "\n\nImporting all of it offers the package's copy over this project's in Unity's dialog, where you can " +
                        "untick it. Import all of it?", "Import all of it", "Cancel") ? Outcome.AsItIs : Outcome.Cancelled;
            }
            finally { EditorUtility.ClearProgressBar(); }
            string said = BundledTools.Words(left, name);
            UnityEngine.Debug.Log("Hoard: " + said);
            string before = add ? Said : null;
            SessionState.SetString(SaidKey, before == null ? said : before + "\n" + said);
            return Outcome.Trimmed;
        }

        /// <summary>The newest version of a tool this project has: through the VCC or Unity's Package Manager (under
        /// Packages/), or in Assets/ (where the project has the tool's package.json, by its GUID, or where this package
        /// would put it). Null when it has none.</summary>
        static string ProjectVersion(BundledTool tool)
        {
            string best = null;
            Action<string> consider = v =>
            {
                int c;
                if (v != null && (best == null || (BundledTools.TryCompare(v, best, out c) && c > 0))) best = v;
            };
            try
            {
                var info = UnityEditor.PackageManager.PackageInfo.FindForAssetPath("Packages/" + tool.Id);
                if (info != null && info.name == tool.Id) consider(info.version);
            }
            catch (Exception) { /* the Package Manager can't say: the files below can */ }
            consider(ManifestVersion(Path.Combine("Packages", tool.Id, "package.json"), tool.Id));
            string at = AssetDatabase.GUIDToAssetPath(tool.ManifestGuid);
            if (!string.IsNullOrEmpty(at)) consider(ManifestVersion(at, tool.Id));
            consider(ManifestVersion(tool.Folder + "/package.json", tool.Id));
            return best;
        }

        /// <summary>The version a package.json in the project gives, when it's this tool's; null otherwise.</summary>
        static string ManifestVersion(string path, string id)
        {
            try
            {
                if (!File.Exists(path) || new FileInfo(path).Length > 64 * 1024) return null;
                string name, version;
                return BundledTools.ReadManifest(File.ReadAllBytes(path), out name, out version) && name == id ? version : null;
            }
            catch (Exception e) when (e is IOException || e is UnauthorizedAccessException || e is ArgumentException) { return null; }
        }
    }
}
