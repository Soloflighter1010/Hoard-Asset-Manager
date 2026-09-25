// Window > Hoard: the assets you've downloaded with the Hoard app, inside Unity. Read-only toward your Hoard
// library: it reads the catalog Hoard writes, and importing hands a .unitypackage to Unity's own import dialog.
using System;
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEngine;

namespace SoloFlighter.Hoard.Editor
{
    public sealed class HoardWindow : EditorWindow
    {
        const string RootPref = "SoloFlighter.Hoard.DownloadsFolder";
        static readonly string[] StoreNames = { "All stores", "Booth", "Gumroad", "Jinxxy", "Payhip", "Itch" };
        static readonly string[] StoreLabels = Array.ConvertAll(StoreNames, s => HoardCatalog.StoreLabel(s));

        const float RowHeight = 52;

        HoardCatalog catalog;                  // null until the first load finishes
        volatile HoardCatalog loaded;          // a load that has finished in the background, waiting to be shown
        bool loading;
        PackageIndex packages;
        List<ImportLog.Entry> log = new List<ImportLog.Entry>();
        readonly ThumbnailCache thumbs = new ThumbnailCache();
        readonly Dictionary<HoardAsset, InProject> statusOf = new Dictionary<HoardAsset, InProject>();
        readonly Dictionary<string, List<HoardAsset>> byPackage = new Dictionary<string, List<HoardAsset>>();
        readonly List<string> fresh = new List<string>();
        List<HoardAsset> shown = new List<HoardAsset>();
        Rect listView;                         // where the list is drawn (known after the first layout)
        HoardAsset filesFor;                   // the product whose files are listed below, and their paths
        List<KeyValuePair<string, string>> files = new List<KeyValuePair<string, string>>();
        HoardAsset selected;
        string search = "";
        int store;
        bool packagesOnly = true, inProjectOnly;
        Vector2 listScroll, detailScroll;
        string importing;           // the file being imported, until Unity says it's done
        HoardAsset importingAsset;

        [MenuItem("Window/Hoard")]
        public static void Open()
        {
            var w = GetWindow<HoardWindow>("Hoard");
            w.minSize = new Vector2(620, 360);
            w.Show();
        }

        void OnEnable()
        {
            packages = new PackageIndex();
            Reload();
            EditorApplication.update += Tick;
            EditorApplication.projectChanged += OnProjectChanged;
            AssetDatabase.importPackageCompleted += OnImportDone;
            AssetDatabase.importPackageCancelled += OnImportEnded;
            AssetDatabase.importPackageFailed += OnImportFailed;
        }

        void OnDisable()
        {
            EditorApplication.update -= Tick;
            EditorApplication.projectChanged -= OnProjectChanged;
            AssetDatabase.importPackageCompleted -= OnImportDone;
            AssetDatabase.importPackageCancelled -= OnImportEnded;
            AssetDatabase.importPackageFailed -= OnImportFailed;
            if (packages != null) packages.Stop();
            thumbs.Clear();
        }

        string DownloadsFolder()
        {
            string chosen = EditorPrefs.GetString(RootPref, "");
            return string.IsNullOrEmpty(chosen) ? HoardLocation.DownloadsFolder() : chosen;
        }

        /// <summary>Read the catalog again, in the background: the window stays usable, and shows the new list when
        /// it's ready.</summary>
        void Reload()
        {
            if (loading) return;
            loading = true;
            string root = DownloadsFolder();
            System.Threading.Tasks.Task.Run(() =>
            {
                var keys = Seal.ReadKeys(HoardLocation.KeyFiles());   // every Hoard key of this user account
                loaded = HoardCatalog.Load(root, keys);
            });
        }

        void Tick()
        {
            var done = loaded;
            if (done != null)
            {
                loaded = null;
                loading = false;
                catalog = done;
                log = ImportLog.Read();
                byPackage.Clear();
                var all = new List<string>();
                foreach (var a in catalog.Assets)
                    foreach (string p in a.PackagePaths)
                    {
                        List<HoardAsset> list;
                        if (!byPackage.TryGetValue(p, out list)) byPackage[p] = list = new List<HoardAsset>();
                        list.Add(a);
                        all.Add(p);
                    }
                statusOf.Clear();
                selected = selected == null ? null : catalog.Assets.Find(a => a.Key == selected.Key);
                filesFor = null;
                packages.Want(all);
                Filter();
                Repaint();
            }
            fresh.Clear();
            if (packages != null && packages.TakeChanges(fresh))
            {
                foreach (string p in fresh)   // only the products whose packages were just read are looked at again
                {
                    List<HoardAsset> list;
                    if (byPackage.TryGetValue(p, out list)) foreach (var a in list) statusOf.Remove(a);
                }
                if (inProjectOnly) Filter();
                Repaint();
            }
            if (thumbs.Pump()) Repaint();
        }

        void OnProjectChanged() { packages.ProjectChanged(); statusOf.Clear(); if (inProjectOnly) Filter(); Repaint(); }

        void OnImportDone(string packageName)
        {
            if (importing != null && importingAsset != null && Path.GetFileNameWithoutExtension(importing) == packageName)
            {
                ImportLog.Record(importingAsset, Path.GetFileName(importing));
                log = ImportLog.Read();
            }
            OnImportEnded(packageName);
        }

        void OnImportEnded(string packageName)
        {
            importing = null;
            importingAsset = null;
            packages.ProjectChanged();
            statusOf.Clear();
            Filter();
            Repaint();
        }

        void OnImportFailed(string packageName, string error)
        {
            Debug.LogWarning("Hoard: importing " + packageName + " failed: " + error);
            OnImportEnded(packageName);
        }

        // ---- what's shown

        InProject ProjectStatus(HoardAsset a)
        {
            InProject known;
            if (statusOf.TryGetValue(a, out known)) return known;
            var best = InProject.Unknown;
            foreach (string p in a.PackagePaths)
            {
                var s = packages.Status(p);
                if (s > best) best = s;
            }
            if (best == InProject.Unknown && ImportLog.Imported(a, log)) best = InProject.Partly;
            statusOf[a] = best;
            return best;
        }

        void Filter()
        {
            shown = new List<HoardAsset>();
            if (catalog == null) return;
            string q = search.Trim().ToLowerInvariant();
            foreach (var a in catalog.Assets)
            {
                if (store > 0 && a.Store != StoreNames[store]) continue;
                if (packagesOnly && !a.HasPackages) continue;
                if (inProjectOnly && ProjectStatus(a) < InProject.Partly) continue;
                if (q.Length > 0 && !a.SearchText.Contains(q)) continue;
                shown.Add(a);
            }
            shown.Sort((x, y) => string.Compare(x.Name, y.Name, StringComparison.CurrentCultureIgnoreCase));
        }

        // ---- drawing

        void OnGUI()
        {
            DrawToolbar();
            if (catalog == null)
            {
                GUILayout.FlexibleSpace();
                GUILayout.Label("Loading your library...", EditorStyles.centeredGreyMiniLabel);
                GUILayout.FlexibleSpace();
                return;
            }
            DrawBanner();
            EditorGUILayout.BeginHorizontal();
            DrawList();
            DrawDetails();
            EditorGUILayout.EndHorizontal();
        }

        void DrawToolbar()
        {
            EditorGUILayout.BeginHorizontal(EditorStyles.toolbar);
            EditorGUI.BeginChangeCheck();
            search = GUILayout.TextField(search, EditorStyles.toolbarSearchField, GUILayout.MinWidth(160));
            store = EditorGUILayout.Popup(store, StoreLabels, EditorStyles.toolbarPopup, GUILayout.Width(100));
            packagesOnly = GUILayout.Toggle(packagesOnly, "Unity packages only", EditorStyles.toolbarButton);
            inProjectOnly = GUILayout.Toggle(inProjectOnly, "In this project", EditorStyles.toolbarButton);
            if (EditorGUI.EndChangeCheck()) Filter();
            GUILayout.FlexibleSpace();
            if (packages.Waiting > 0) GUILayout.Label("Checking packages: " + packages.Waiting + " to go", EditorStyles.miniLabel);
            if (loading && catalog != null) GUILayout.Label("Loading...", EditorStyles.miniLabel);
            if (GUILayout.Button("Reload", EditorStyles.toolbarButton)) Reload();
            if (GUILayout.Button("Folder...", EditorStyles.toolbarButton))
            {
                string picked = EditorUtility.OpenFolderPanel("Hoard's downloads folder", DownloadsFolder(), "");
                if (!string.IsNullOrEmpty(picked))
                {
                    EditorPrefs.SetString(RootPref, picked == HoardLocation.DownloadsFolder() ? "" : picked);
                    Reload();
                }
            }
            EditorGUILayout.EndHorizontal();
        }

        void DrawBanner()
        {
            if (catalog.Problem != null)
            {
                EditorGUILayout.HelpBox(catalog.Problem + "\nLooking in: " + catalog.Root, MessageType.Info);
                return;
            }
            if (catalog.SealStatus == SealState.Changed)
                EditorGUILayout.HelpBox("catalog.json was changed by something other than Hoard, so importing is paused and store links are hidden. " +
                                        "Open Hoard and choose Sync (or run Hoard.bat verify) to rebuild it.", MessageType.Warning);
            else if (catalog.SealStatus == SealState.Foreign)
                EditorGUILayout.HelpBox("catalog.json was sealed with a Hoard key this account doesn't have (Hoard on another computer, " +
                                        "or an earlier Hoard install), so it can't be checked here. Opening Hoard seals it again with this " +
                                        "computer's key, then choose Reload.", MessageType.Info);
            if (catalog.LeftOut > 0)
                EditorGUILayout.HelpBox(catalog.LeftOut + " entries in catalog.json didn't look right and were left out.", MessageType.None);
        }

        void DrawList()
        {
            float width = Mathf.Max(280, position.width * 0.45f);
            EditorGUILayout.BeginVertical(GUILayout.Width(width));
            GUILayout.Label(shown.Count + " of " + catalog.Assets.Count + " downloaded products", EditorStyles.miniLabel);
            Rect view = GUILayoutUtility.GetRect(width, 10, GUILayout.ExpandWidth(true), GUILayout.ExpandHeight(true));
            if (Event.current.type != EventType.Layout) listView = view;   // the layout pass doesn't know it yet
            var content = new Rect(0, 0, Mathf.Max(0, listView.width - 16), shown.Count * RowHeight);
            listScroll = GUI.BeginScrollView(listView, listScroll, content);
            int first, last;   // only what's on screen is drawn, however long the list
            ListView.VisibleRange(listScroll.y, listView.height, RowHeight, shown.Count, out first, out last);
            for (int i = first; i <= last; i++)
            {
                var a = shown[i];
                var row = new Rect(0, i * RowHeight, content.width, RowHeight);
                if (a == selected) EditorGUI.DrawRect(row, EditorGUIUtility.isProSkin ? new Color(0.24f, 0.37f, 0.59f) : new Color(0.6f, 0.75f, 1f));
                var t = thumbs.Get(a.ThumbPath);
                var pic = new Rect(row.x + 4, row.y + 4, 44, 44);
                if (t != null) GUI.DrawTexture(pic, t, ScaleMode.ScaleAndCrop);
                else EditorGUI.DrawRect(pic, new Color(0.3f, 0.3f, 0.3f, 0.5f));
                GUI.Label(new Rect(row.x + 56, row.y + 6, row.width - 150, 18), a.Name, EditorStyles.boldLabel);
                GUI.Label(new Rect(row.x + 56, row.y + 26, row.width - 150, 18), a.Creator + "  ·  " + HoardCatalog.StoreLabel(a.Store), EditorStyles.miniLabel);
                var s = ProjectStatus(a);
                if (s >= InProject.Partly)
                    GUI.Label(new Rect(row.xMax - 92, row.y + 16, 88, 18), s == InProject.Yes ? "In this project" : "Partly in project", EditorStyles.miniBoldLabel);
                if (Event.current.type == EventType.MouseDown && row.Contains(Event.current.mousePosition))
                {
                    selected = a;
                    detailScroll = Vector2.zero;
                    Event.current.Use();
                    Repaint();
                }
            }
            GUI.EndScrollView();
            EditorGUILayout.EndVertical();
        }

        void DrawDetails()
        {
            EditorGUILayout.BeginVertical();
            if (selected == null)
            {
                GUILayout.FlexibleSpace();
                GUILayout.Label("Choose a product on the left.", EditorStyles.centeredGreyMiniLabel);
                GUILayout.FlexibleSpace();
                EditorGUILayout.EndVertical();
                return;
            }
            var a = selected;
            detailScroll = EditorGUILayout.BeginScrollView(detailScroll);
            var t = thumbs.Get(a.ThumbPath);
            if (t != null) GUI.DrawTexture(GUILayoutUtility.GetRect(160, 160, GUILayout.Width(160), GUILayout.Height(160)), t, ScaleMode.ScaleToFit);
            if (filesFor != a)   // the selected product's files are looked up once, not on every repaint
            {
                filesFor = a;
                files = a.Files.ConvertAll(f => new KeyValuePair<string, string>(f, catalog.FilePath(a, f)));
            }
            GUILayout.Label(a.Name, EditorStyles.largeLabel);
            GUILayout.Label("by " + a.Creator + "  ·  " + HoardCatalog.StoreLabel(a.Store) + (a.Variants != null ? "  ·  " + a.Variants : ""), EditorStyles.label);
            if (a.Tags.Count > 0) GUILayout.Label("Tags: " + string.Join(", ", a.Tags), EditorStyles.wordWrappedMiniLabel);
            EditorGUILayout.Space();

            bool paused = catalog.SealStatus == SealState.Changed || importing != null || EditorApplication.isCompiling;
            foreach (var entry in files)
            {
                string file = entry.Key, path = entry.Value;
                EditorGUILayout.BeginHorizontal(EditorStyles.helpBox);
                GUILayout.Label(file, EditorStyles.wordWrappedLabel);
                if (path == null) { GUILayout.Label("missing", EditorStyles.miniLabel, GUILayout.Width(60)); EditorGUILayout.EndHorizontal(); continue; }
                bool unityPackage = file.EndsWith(".unitypackage", StringComparison.OrdinalIgnoreCase);
                if (unityPackage)
                {
                    int have, total;
                    var s = packages.Status(path, out have, out total);
                    if (s != InProject.Unknown) GUILayout.Label(have + " of " + total + " here", EditorStyles.miniLabel, GUILayout.Width(80));
                    EditorGUI.BeginDisabledGroup(paused);
                    if (GUILayout.Button(s == InProject.Yes ? "Import again" : "Import", GUILayout.Width(90))) Import(a, path);
                    EditorGUI.EndDisabledGroup();
                    if (have > 0 && GUILayout.Button("Select", GUILayout.Width(60))) SelectInProject(path);
                }
                if (GUILayout.Button("Show", GUILayout.Width(50))) EditorUtility.RevealInFinder(path);
                EditorGUILayout.EndHorizontal();
            }
            EditorGUILayout.Space();
            EditorGUILayout.BeginHorizontal();
            string folder = catalog.FolderPath(a);
            if (folder != null && GUILayout.Button("Open folder", GUILayout.Width(100))) EditorUtility.RevealInFinder(folder);
            if (HoardCatalog.StoreLink(a.Store, a.Url) && GUILayout.Button("Store page", GUILayout.Width(100))) Application.OpenURL(a.Url);
            EditorGUILayout.EndHorizontal();
            EditorGUILayout.EndScrollView();
            EditorGUILayout.EndVertical();
        }

        void Import(HoardAsset a, string path)
        {
            importing = path;
            importingAsset = a;
            AssetDatabase.ImportPackage(path, true);   // Unity's own dialog: you choose what comes in
        }

        void SelectInProject(string packagePath)
        {
            var found = new List<UnityEngine.Object>();
            foreach (string g in packages.Guids(packagePath))
            {
                string p = AssetDatabase.GUIDToAssetPath(g);
                if (string.IsNullOrEmpty(p)) continue;
                var o = AssetDatabase.LoadMainAssetAtPath(p);
                if (o != null && !AssetDatabase.IsValidFolder(p)) found.Add(o);
            }
            Selection.objects = found.ToArray();
            if (found.Count > 0) EditorGUIUtility.PingObject(found[0]);
        }
    }
}
