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

        /// <summary>The file to import: the package as it is, or a copy of it without the tools this project has at
        /// the same version or a newer one (in Library/Hoard/Trimmed). add: one of a set's packages, so what it leaves
        /// out is said with what the others did.</summary>
        public static string Prepare(string file, bool add)
        {
            if (!add) Forget();
            string name = Path.GetFileName(file);
            try
            {
                EditorUtility.DisplayProgressBar("Hoard", "Looking at what's in " + name, 0.3f);
                Dictionary<string, byte[]> manifests;
                var assets = UnityPackageReader.ReadAssetsAndManifests(file, out manifests);
                var found = BundledTools.Find(assets, manifests);
                if (found.Count == 0) return file;
                foreach (var tool in found) tool.InProject = ProjectVersion(tool);
                var left = BundledTools.LeftOut(found);
                if (left.Count == 0) return file;
                EditorUtility.DisplayProgressBar("Hoard", "Leaving out what this project has already", 0.6f);
                string trimmed = PackageTrim.Without(file, BundledTools.GuidsOf(left), Path.Combine("Library", "Hoard", "Trimmed"));
                string said = BundledTools.Words(left, name);
                UnityEngine.Debug.Log("Hoard: " + said);
                string before = add ? Said : null;
                SessionState.SetString(SaidKey, before == null ? said : before + "\n" + said);
                return trimmed;
            }
            catch (Exception e)   // not a package Hoard can read, or the copy couldn't be made: Unity's dialog offers it as it is
            {
                UnityEngine.Debug.LogWarning("Hoard: couldn't look at the tools " + name + " carries (" + e.Message + "), so all of it is offered.");
                return file;
            }
            finally { EditorUtility.ClearProgressBar(); }
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
