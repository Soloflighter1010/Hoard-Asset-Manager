// Hoard › Open Hoard (its own menu in Unity's menu bar): the assets you've downloaded with the Hoard app, inside Unity. Read-only toward your Hoard
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
        static readonly string[] StoreNames = Prepend("All stores", HoardCatalog.Stores);   // the catalog's own list

        static string[] Prepend(string first, string[] rest)
        {
            var all = new string[rest.Length + 1];
            all[0] = first;
            Array.Copy(rest, 0, all, 1, rest.Length);
            return all;
        }

        const string SizePref = "SoloFlighter.Hoard.TileSize";
        const string PausePref = "SoloFlighter.Hoard.PauseAnimations";
        const string PauseLabel = "Pause GIFs";
        const float BarHeight = 50, TabsHeight = 40, ToolsHeight = 34, Pad = 18, Gap = 16;
        const int SmallestTile = 96, BiggestTile = 200;

        HoardCatalog catalog;                  // null until the first load finishes
        volatile HoardCatalog loaded;          // a load that has finished in the background, waiting to be shown
        bool loading;
        PackageIndex packages;
        List<ImportLog.Entry> log = new List<ImportLog.Entry>();
        readonly ThumbnailCache thumbs = new ThumbnailCache();
        readonly Dictionary<HoardAsset, InProject> statusOf = new Dictionary<HoardAsset, InProject>();
        readonly Dictionary<HoardAsset, string> newerOf = new Dictionary<HoardAsset, string>();   // a newer download to import, or ""
        Dictionary<string, int> pending = new Dictionary<string, int>();   // updates Hoard's last check found, by Updates.Key
        volatile Dictionary<string, int> loadedPending;
        DateTime pendingRead;      // when asset-updates.json was last read, to read it again only when it's changed
        List<Origin> origins;      // "Which Product Is This From?": what the asked-about files came from, until closed
        string[] originGuids;      // the files asked about (a folder's, for a folder)
        readonly Dictionary<string, List<HoardAsset>> byPackage = new Dictionary<string, List<HoardAsset>>();
        readonly List<string> fresh = new List<string>();
        List<HoardAsset> shown = new List<HoardAsset>();
        Rect gridView;                         // where the tiles are drawn, how many to a row, and each row's height
        int gridColumns = 1;
        float gridRow = 200;
        int[] counts = new int[0];             // how many each store's tab has, with the other filters
        int tileSize = 132;
        readonly Dictionary<HoardAsset, KeyValuePair<float, string>> nameFits = new Dictionary<HoardAsset, KeyValuePair<float, string>>();
        HoardAsset filesFor;                   // the product whose files are listed below, and their paths
        List<KeyValuePair<string, string>> files = new List<KeyValuePair<string, string>>();
        HoardAsset selected;
        string search = "";
        int store;
        bool packagesOnly = true, inProjectOnly, updatesOnly;
        Vector2 gridScroll, detailScroll;
        bool reportDue;             // what this project uses has changed: tell Hoard's Projects view (issue #86)
        double reportAfter;
        string lastReport;

        // Hoard's own menu in Unity's menu bar, as other tools for VRChat creators have theirs
        [MenuItem("Hoard/Open Hoard", false, 0)]
        public static void Open() { OpenWindow(); }

        static HoardWindow OpenWindow()
        {
            var w = GetWindow<HoardWindow>("Hoard");
            w.minSize = new Vector2(620, 360);
            w.Show();
            return w;
        }

        [MenuItem("Hoard/Create Credits List", false, 1)]
        static void OpenCredits() { CreditsWindow.Open(OpenWindow()); }

        void OnEnable()
        {
            packages = new PackageIndex();
            tileSize = Mathf.Clamp(EditorPrefs.GetInt(SizePref, 132), SmallestTile, BiggestTile);
            thumbs.Paused = EditorPrefs.GetBool(PausePref, false);
            wantsMouseMove = true;   // the app's hover: a tile lifts, a button lights
            Reload();
            EditorApplication.update += Tick;
            EditorApplication.projectChanged += OnProjectChanged;
            PendingImport.Ended += OnImportEnded;   // (kept there, not here: it outlives the scripts reloading)
        }

        void OnDisable()
        {
            EditorApplication.update -= Tick;
            EditorApplication.projectChanged -= OnProjectChanged;
            PendingImport.Ended -= OnImportEnded;
            if (packages != null) packages.Stop();
            thumbs.Clear();
            Look.Release();
        }

        string DownloadsFolder()
        {
            string chosen = EditorPrefs.GetString(RootPref, "");
            return string.IsNullOrEmpty(chosen) ? HoardLocation.DownloadsFolder() : chosen;
        }

        /// <summary>Read the catalog again, in the background: the window stays usable, and shows the new list when
        /// it's ready. Asked again during a load (another folder chosen), the newer one is what's shown.</summary>
        void Reload()
        {
            loading = true;
            int mine = System.Threading.Interlocked.Increment(ref generation);
            string root;
            try { root = DownloadsFolder(); }
            catch (Exception e) { root = null; Debug.LogWarning("Hoard: couldn't find Hoard's downloads folder: " + e.Message); }
            System.Threading.Tasks.Task.Run(() =>
            {
                HoardCatalog cat;
                try
                {
                    if (root == null) throw new IOException("no downloads folder");
                    var keys = Seal.ReadKeys(HoardLocation.KeyFiles());   // every Hoard key of this user account
                    cat = HoardCatalog.Load(root, keys);
                    loadedPending = ReadPending();
                }
                catch (Exception e)   // never left "Loading your library..." for good
                {
                    cat = new HoardCatalog { Root = root ?? "", Problem = "Hoard's library couldn't be read here (" + e.Message + ")." };
                }
                if (mine == generation) loaded = cat;   // an older load finishing late isn't shown
            });
        }

        int generation;

        void Tick()
        {
            var done = loaded;
            if (done != null)
            {
                loaded = null;
                loading = false;
                catalog = done;
                log = ImportLog.Read();
                if (loadedPending != null) { pending = loadedPending; loadedPending = null; }
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
                var owners = new Dictionary<string, string>();   // a package two products list is both of theirs
                foreach (var kv in byPackage)
                {
                    var keys = kv.Value.ConvertAll(a => a.Key);
                    keys.Sort(StringComparer.Ordinal);
                    owners[kv.Key] = string.Join("\n", keys);
                }
                packages.SetOwners(owners);
                Forget();
                packages.ProjectChanged();   // a package downloaded again since is counted again
                selected = selected == null ? null : catalog.Assets.Find(a => a.Key == selected.Key);
                filesFor = null;
                packages.Want(all);
                Filter();
                Repaint();
                ReportSoon();
                if (originGuids != null) FindOrigins();   // asked before the library was loaded
            }
            fresh.Clear();
            if (packages != null && packages.TakeChanges(fresh))
            {
                if (packages.SharingChanged) Forget();   // files shared with others: every product may change
                else foreach (string p in fresh)   // only the products whose packages were just read are looked at again
                {
                    List<HoardAsset> list;
                    if (byPackage.TryGetValue(p, out list)) foreach (var a in list) Forget(a);
                }
                if (inProjectOnly || updatesOnly) Filter();
                Repaint();
                ReportSoon();
            }
            if (reportDue && catalog != null && packages != null && packages.Waiting == 0
                && EditorApplication.timeSinceStartup >= reportAfter)
                Report();
            if (thumbs.Pump()) Repaint();
            else if (thumbs.Animating && EditorApplication.timeSinceStartup - animatedAt > 1.0 / 30)
            {
                animatedAt = EditorApplication.timeSinceStartup;   // an animated picture is showing: play it
                Repaint();
            }
        }

        double animatedAt;

        void OnProjectChanged() { packages.ProjectChanged(); Forget(); if (inProjectOnly || updatesOnly) Filter(); Repaint(); ReportSoon(); }

        /// <summary>Tell Hoard what this project uses, a moment after the last change (once its packages are read).</summary>
        public void ReportSoon()
        {
            reportDue = true;
            reportAfter = EditorApplication.timeSinceStartup + 3;
        }

        /// <summary>Hoard's Projects view (issue #86): every product in this project, and how much of it, with the credits
        /// settings, written to projects/ in Hoard's own folder. Written when it first settles in a session (so Hoard
        /// knows when you last had the project open), and after that only when something in it changed.</summary>
        void Report()
        {
            reportDue = false;
            if (catalog.Problem != null) return;   // no Hoard library here (yet): nothing to tell it
            log = ImportLog.Read();
            Forget();
            var used = new List<ProjectAsset>();
            foreach (var a in catalog.Assets)
            {
                var s = ProjectStatus(a);
                bool logged = s == InProject.Partly && !a.PackagePaths.Exists(p => packages.Status(p) == InProject.Partly);
                if (s >= InProject.Partly)
                    used.Add(new ProjectAsset { Store = a.Store, Name = a.Name, Creator = a.Creator, Folder = a.Folder, Url = a.Url,
                                                Status = s == InProject.Yes ? "yes" : logged ? "imported" : "partly" });
            }
            string project = Directory.GetCurrentDirectory();
            string name = string.IsNullOrWhiteSpace(PlayerSettings.productName) ? Path.GetFileName(project) : PlayerSettings.productName;
            var credits = CreditsFile.Load(CreditsWindow.SettingsFile);
            byte[] stamped;
            string body = System.Text.Encoding.UTF8.GetString(ProjectReport.Build(project, name, Application.unityVersion, used, credits,
                DateTime.UtcNow.ToString("yyyy-MM-dd'T'HH:mm:ss'+00:00'", System.Globalization.CultureInfo.InvariantCulture), out stamped));
            if (body == lastReport) return;
            try
            {
                ProjectReport.Write(ProjectReport.FileFor(HoardLocation.DataDir(), project), stamped);
                lastReport = body;
            }
            catch (Exception e) when (e is IOException || e is UnauthorizedAccessException)
            {
                Debug.LogWarning("Hoard: couldn't tell Hoard what this project uses: " + e.Message);
            }
        }

        void OnImportEnded()
        {
            log = ImportLog.Read();
            if (packages != null) packages.ProjectChanged();
            Forget();
            Filter();
            Repaint();
            ReportSoon();
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

        void Forget() { statusOf.Clear(); newerOf.Clear(); }

        void Forget(HoardAsset a) { statusOf.Remove(a); newerOf.Remove(a); }

        /// <summary>A newer download of this product than what the project has, to import: its package, or null.
        /// Only for products in the project; worked out once, like their status.</summary>
        string NewerDownload(HoardAsset a)
        {
            string known;
            if (newerOf.TryGetValue(a, out known)) return known.Length == 0 ? null : known;
            string newer = null;
            if (ProjectStatus(a) >= InProject.Partly && a.PackagePaths.Count > 0)
            {
                var states = new List<PackageState>();
                foreach (string p in a.PackagePaths)
                {
                    try { states.Add(new PackageState { Path = p, Written = PackageFile.LastWriteUtc(p), AllHere = packages.Status(p) == InProject.Yes }); }
                    catch (Exception) { /* gone since the library was read */ }
                }
                DateTime? lastImport = null;
                foreach (var e in log)
                    if (e.Store == a.Store && e.Name == a.Name)
                    {
                        var t = Updates.ParseTime(e.ImportedAt);
                        if (t.HasValue && (!lastImport.HasValue || t.Value > lastImport.Value)) lastImport = t;
                    }
                newer = Updates.NewerPackage(states, lastImport);
            }
            newerOf[a] = newer ?? "";
            return newer;
        }

        /// <summary>How many new or changed files Hoard's last check for updates found for this product, when it's in
        /// the project and the update isn't downloaded yet (0 otherwise).</summary>
        int UpdateInHoard(HoardAsset a)
        {
            int n;
            return ProjectStatus(a) >= InProject.Partly && pending.TryGetValue(Updates.Key(a.Store, a.Name), out n) ? n : 0;
        }

        static Dictionary<string, int> ReadPending()
        {
            try
            {
                string file = Path.Combine(HoardLocation.DataDir(), "asset-updates.json");
                if (!File.Exists(file) || new FileInfo(file).Length > 32L * 1024 * 1024) return new Dictionary<string, int>();
                return Updates.ReadPending(File.ReadAllText(file, System.Text.Encoding.UTF8));
            }
            catch (Exception) { return new Dictionary<string, int>(); }   // only ever a hint
        }

        /// <summary>Back in the window (after checking for updates in Hoard, say): read Hoard's update list again if
        /// it's changed.</summary>
        void OnFocus()
        {
            try
            {
                string file = Path.Combine(HoardLocation.DataDir(), "asset-updates.json");
                DateTime written = File.Exists(file) ? File.GetLastWriteTimeUtc(file) : DateTime.MinValue;
                if (written == pendingRead) return;
                pendingRead = written;
                pending = ReadPending();
                if (updatesOnly) Filter();
                Repaint();
            }
            catch (Exception) { /* the next look will do */ }
        }

        // ---- "Which Product Is This From?" (Assets menu, and the Project window's right-click menu)

        [MenuItem("Hoard/Which Product Is This From?", false, 20)]
        [MenuItem("Assets/Hoard/Which Product Is This From?", false, 1500)]
        static void WhichProduct()
        {
            var guids = Selection.assetGUIDs;
            if (guids == null || guids.Length == 0) return;
            var w = OpenWindow();
            w.originGuids = guids;
            w.FindOrigins();
        }

        [MenuItem("Hoard/Which Product Is This From?", true)]
        [MenuItem("Assets/Hoard/Which Product Is This From?", true)]
        static bool CanWhichProduct() { return Selection.assetGUIDs != null && Selection.assetGUIDs.Length > 0; }

        const int MaxAskedFiles = 20000;

        void FindOrigins()
        {
            if (catalog == null || originGuids == null) return;   // looked up when the library has loaded
            var files = new HashSet<string>();
            foreach (string g in originGuids)
            {
                string path = AssetDatabase.GUIDToAssetPath(g);
                if (string.IsNullOrEmpty(path)) continue;
                if (AssetDatabase.IsValidFolder(path))   // a folder: the files in it, which is what packages list
                {
                    foreach (string inside in AssetDatabase.FindAssets("", new[] { path }))
                        if (files.Count < MaxAskedFiles && !AssetDatabase.IsValidFolder(AssetDatabase.GUIDToAssetPath(inside))) files.Add(inside);
                }
                else if (files.Count < MaxAskedFiles) files.Add(g);
            }
            originFiles = files.Count;
            origins = packages.OriginsOf(files);
            Repaint();
        }

        int originFiles;

        /// <summary>What "Which Product Is This From?" found, in a box above the tiles. Returns where the next thing goes.</summary>
        float DrawOrigins(float y)
        {
            if (origins == null) return y;
            float w = position.width - Pad * 2;
            string still = packages.Waiting > 0 ? " Hoard is still reading " + packages.Waiting + " packages, so look again in a moment." : "";
            string files = originFiles == 1 ? "this file" : "these " + originFiles + " files";
            string text = origins.Count == 0 ? "None of " + files + " came from a package Hoard downloaded." + still
                                             : "Where " + files + " came from:" + still;
            var rows = new List<HoardAsset>();
            var found = new List<int>();
            for (int i = 0; i < origins.Count && rows.Count < 5; i++)
            {
                var a = catalog.Assets.Find(x => x.Key == origins[i].Product);
                if (a != null) { rows.Add(a); found.Add(origins[i].Count); }
            }
            var wrapped = Look.Style(Look.Styles.Wrapped);
            float buttons = Look.ButtonWidth("Look again") + 6 + 30;
            float textH = Mathf.Max(Look.ButtonHeight, wrapped.CalcHeight(new GUIContent(text), w - 24 - buttons));
            var box = new Rect(Pad, y + 8, w, 20 + textH + rows.Count * 30);
            if (Event.current.type == EventType.Repaint) Look.Box("origins", Look.Ledge, Look.Seam).Draw(box, false, false, false, false);
            Look.Fill(new Rect(box.x, box.y + 8, 3, box.height - 16), Look.Gold, 1.5f);
            GUI.Label(new Rect(box.x + 14, box.y + 10, w - 24 - buttons, textH), text, wrapped);
            float bx = box.xMax - 10 - buttons + 6;
            if (Look.Button(new Rect(bx, box.y + 10, Look.ButtonWidth("Look again"), Look.ButtonHeight), "Look again")) FindOrigins();
            if (Look.Button(new Rect(box.xMax - 10 - 26, box.y + 10, 26, Look.ButtonHeight), new GUIContent("×", "Close"), Look.Kind.Ghost))
            {
                origins = null;
                originGuids = null;
                return y;
            }
            float ry = box.y + 14 + textH;
            for (int i = 0; i < rows.Count; i++, ry += 30)
            {
                var a = rows[i];
                Look.Dot(new Vector2(box.x + 20, ry + 13), Look.Store(a.Store));
                float showW = Look.ButtonWidth("Show"), countW = 70;
                FittedLabel(new Rect(box.x + 32, ry + 4, w - 52 - showW - countW, 18), a.Name + "  ·  " + a.Creator + "  ·  " + HoardCatalog.StoreLabel(a.Store),
                            Look.Style("originName", Look.Styles.Name));
                GUI.Label(new Rect(box.xMax - 14 - showW - countW, ry + 5, countW - 6, 18), found[i] + (found[i] == 1 ? " file" : " files"), Look.Style(Look.Styles.Small));
                if (Look.Button(new Rect(box.xMax - 10 - showW, ry, showW, Look.ButtonHeight), "Show")) ShowProduct(a);
            }
            return box.yMax;
        }

        /// <summary>Select a product, with the filters cleared so it's there to see.</summary>
        void ShowProduct(HoardAsset a)
        {
            search = "";
            store = 0;
            if (!a.HasPackages) packagesOnly = false;
            inProjectOnly = updatesOnly = false;
            Filter();
            Select(a, true);
        }

        void Select(HoardAsset a, bool scrollTo)
        {
            selected = a;
            detailScroll = Vector2.zero;
            int at = a == null ? -1 : shown.IndexOf(a);
            if (scrollTo && at >= 0)
            {
                float top = Pad + (at / Mathf.Max(1, gridColumns)) * gridRow;
                if (top < gridScroll.y) gridScroll.y = Mathf.Max(0, top - Pad);
                else if (top + gridRow > gridScroll.y + gridView.height) gridScroll.y = top + gridRow - gridView.height + Pad;
            }
            Repaint();
        }

        /// <summary>For the credits list (issues #51 and #79): the products this project uses. Only a product with
        /// one of its packages fully in the project counts: one that's partly there, or that the import log alone
        /// says was imported, isn't credited (it may have been removed, or only a piece of it kept). Products
        /// added by hand in the Credits window are kept there. stillChecking: packages not read yet, so the list
        /// may grow.</summary>
        public List<CreditEntry> UsedInProject(out int stillChecking, out bool ready)
        {
            var found = new List<CreditEntry>();
            stillChecking = packages == null ? 0 : packages.Waiting;
            ready = catalog != null;
            if (catalog == null) return found;
            log = ImportLog.Read();
            Forget();   // the project may have changed since the list was drawn
            foreach (var a in catalog.Assets)
                if (ProjectStatus(a) == InProject.Yes)
                    found.Add(new CreditEntry { Store = a.Store, Name = a.Name, Creator = a.Creator, Url = a.Url });
            return found;
        }

        void Filter()
        {
            shown = new List<HoardAsset>();
            counts = new int[StoreNames.Length];
            if (catalog == null) return;
            string q = search.Trim().ToLowerInvariant();
            foreach (var a in catalog.Assets)
            {
                if (packagesOnly && !a.HasPackages) continue;
                if (inProjectOnly && ProjectStatus(a) < InProject.Partly) continue;
                if (updatesOnly && NewerDownload(a) == null && UpdateInHoard(a) == 0) continue;
                if (q.Length > 0 && !a.SearchText.Contains(q)) continue;
                counts[0]++;   // each store's tab counts what the other filters leave, as the app's do
                int at = Array.IndexOf(StoreNames, a.Store);
                if (at > 0) counts[at]++;
                if (store > 0 && a.Store != StoreNames[store]) continue;
                shown.Add(a);
            }
            shown.Sort((x, y) => string.Compare(x.Name, y.Name, StringComparison.CurrentCultureIgnoreCase));
        }

        // ---- drawing: the app's library, in Unity. The bar (logo, search, tools), the store tabs with the filters,
        // the tiles, and the chosen product's details beside them.

        void OnGUI()
        {
            if (Event.current.type == EventType.MouseMove) Repaint();   // hover: a tile lifts, a button lights
            float w = position.width, h = position.height;
            Look.Fill(new Rect(0, 0, w, h), Look.Cave);
            float y = DrawBar();
            if (catalog == null)
            {
                DrawEmpty(new Rect(0, y, w, h - y), "Loading your library…", "Hoard for Unity reads the catalog the Hoard app keeps.", false);
                return;
            }
            y = DrawShelf(y);
            y = DrawNotices(y);
            y = DrawOrigins(y);
            float panel = selected == null ? 0 : Mathf.Clamp(w * 0.38f, 300, 460);
            // a window too narrow for the tiles beside the details: the details cover them, as in the app on a small
            // screen, until they're closed
            if (panel > 0 && w - panel < Mathf.Max(260, tileSize + Pad * 2 + 54)) panel = w;
            var grid = new Rect(0, y, w - panel, h - y);
            if (grid.width > 0) DrawGrid(grid);
            if (selected != null) DrawDetails(new Rect(w - panel, y, panel, h - y));
            Keys();
        }

        float DrawBar()
        {
            float w = position.width;
            string[] tools = { "Create Credits List", "Reload", "Folder..." };
            float toolsW = 0;
            foreach (string t in tools) toolsW += Look.ButtonWidth(t) + 6;
            bool compact = w < 720;   // a narrow window: just the logo's boxes, and shorter words when the search needs room
            if (w - 16 - toolsW - 12 - (16 + (compact ? 24 : 85) + 18) < 160)
            {
                tools[0] = "Credits";
                toolsW = 0;
                foreach (string t in tools) toolsW += Look.ButtonWidth(t) + 6;
            }
            float x = 16;
            x += Look.DrawLogo(new Vector2(x, 13), 24, compact) + 18;
            float right = w - 16 - toolsW;
            DrawSearch(new Rect(x, 11, Mathf.Clamp(right - 12 - x, 80, 440), 28));
            float bx = w - 16 - toolsW + 6;
            var tips = new[] { "A list of the creators of the Hoard products in this project, to credit them",
                               "Read Hoard's library again", "Choose where Hoard's downloads are, if not where Hoard keeps them" };
            for (int i = 0; i < tools.Length; i++)
            {
                var r = new Rect(bx, 12, Look.ButtonWidth(tools[i]), Look.ButtonHeight);
                bx += r.width + 6;
                if (!Look.Button(r, new GUIContent(tools[i], tips[i]), Look.Kind.Ghost)) continue;
                if (i == 0) CreditsWindow.Open(this);
                else if (i == 1) Reload();
                else
                {
                    string picked = EditorUtility.OpenFolderPanel("Hoard's downloads folder", DownloadsFolder(), "");
                    if (!string.IsNullOrEmpty(picked))
                    {
                        EditorPrefs.SetString(RootPref, SamePath(picked, HoardLocation.DownloadsFolder()) ? "" : picked);
                        Reload();
                    }
                    GUIUtility.ExitGUI();   // the folder dialog ran in the middle of drawing
                }
            }
            return BarHeight;
        }

        const string SearchControl = "HoardSearch";

        void DrawSearch(Rect r)
        {
            bool focused = GUI.GetNameOfFocusedControl() == SearchControl;
            Look.Fill(r, Look.Ledge, 10);
            Look.Outline(r, focused ? Look.Gold : Look.Seam, focused ? 2 : 1, 10);
            // a magnifier: a ring, and its handle
            var ring = new Rect(r.x + 10, r.y + 8, 10, 10);
            Look.Outline(ring, Look.Dust, 2, 5);
            if (Event.current.type == EventType.Repaint)
            {
                var m = GUI.matrix;
                var at = new Vector2(ring.xMax - 1.5f, ring.yMax - 1.5f);
                GUIUtility.RotateAroundPivot(45, at);
                Look.Fill(new Rect(at.x, at.y - 1, 5, 2), Look.Dust, 1);
                GUI.matrix = m;
            }
            var field = new Rect(r.x + 28, r.y + 1, r.width - 28 - 26, r.height - 2);
            EditorGUI.BeginChangeCheck();
            GUI.SetNextControlName(SearchControl);
            search = GUI.TextField(field, search, Look.SearchField);
            if (EditorGUI.EndChangeCheck()) { Filter(); gridScroll = Vector2.zero; }
            if (search.Length == 0 && !focused)
            {
                var hint = Look.Style("placeholder", Look.Styles.Dust);
                hint.alignment = TextAnchor.MiddleLeft;
                hint.padding = new RectOffset(0, 0, 0, 0);
                GUI.Label(field, "Search your hoard    /", hint);
            }
            if (search.Length > 0)
            {
                var clear = Look.Style("clear", Look.Styles.Dust);
                clear.alignment = TextAnchor.MiddleCenter;
                clear.fontSize = 15;
                if (GUI.Button(new Rect(r.xMax - 26, r.y + 2, 22, r.height - 4), new GUIContent("×", "Clear the search"), clear))
                {
                    search = "";
                    GUI.FocusControl(null);
                    Filter();
                }
            }
        }

        string TabLabel(int i) { return i == 0 ? "Everything" : HoardCatalog.StoreLabel(StoreNames[i]); }

        string TabCount(int i) { return (i < counts.Length ? counts[i] : 0).ToString("N0"); }

        float TabWidth(int i, bool withCount)
        {
            float wd = 28 + Look.Style("tab", Look.Styles.Tab).CalcSize(new GUIContent(TabLabel(i))).x + (i > 0 ? 15 : 0);
            if (withCount) wd += 6 + Look.Style(Look.Styles.TabCount).CalcSize(new GUIContent(TabCount(i))).x;
            return wd;
        }

        /// <summary>The shelf: a folder tab for each store, the shown one raised and open into the tiles, with the
        /// filters and the tile size beside them (above them, when there isn't room beside).</summary>
        float DrawShelf(float y)
        {
            float w = position.width;
            var tabs = new List<int>();
            for (int i = 0; i < StoreNames.Length; i++)
                if (i == 0 || i == store || (i < counts.Length && counts[i] > 0)) tabs.Add(i);
            bool withCounts = true;
            float tabsW = 0;
            foreach (int i in tabs) tabsW += TabWidth(i, true) + 4;
            if (tabsW > w - Pad * 2)   // narrow: the tabs without their counts
            {
                withCounts = false;
                tabsW = 0;
                foreach (int i in tabs) tabsW += TabWidth(i, false) + 4;
            }
            string[] pills = { "Unity packages only", "In this project", "Updates" };
            string[] pillTips = { "Only products with a .unitypackage to import", "Only products whose files are in this project",
                                  "Products in this project with a newer download, or an update waiting in Hoard" };
            float pillsW = 0;
            foreach (string p in pills) pillsW += Look.ButtonWidth(p) - 4 + 6;
            float toolsW = pillsW + 12 + 110 + 12 + Look.ButtonWidth(PauseLabel) - 4;
            bool above = tabsW + toolsW + 12 > w - Pad * 2;
            float tabsTop = above ? y + ToolsHeight : y, bottom = tabsTop + TabsHeight;

            // the filters, and the tile size
            float tx = above ? Pad : w - Pad - toolsW, ty = above ? y + 6 : bottom - 31;
            EditorGUI.BeginChangeCheck();
            for (int i = 0; i < pills.Length; i++)
            {
                bool on = i == 0 ? packagesOnly : i == 1 ? inProjectOnly : updatesOnly;
                var r = new Rect(tx, ty, Look.ButtonWidth(pills[i]) - 4, 24);
                tx += r.width + 6;
                if (Look.Button(r, new GUIContent(pills[i], pillTips[i]), on ? Look.Kind.PillOn : Look.Kind.Pill))
                {
                    if (i == 0) packagesOnly = !packagesOnly;
                    else if (i == 1) inProjectOnly = !inProjectOnly;
                    else updatesOnly = !updatesOnly;
                    GUI.changed = true;
                }
            }
            if (EditorGUI.EndChangeCheck()) { Filter(); gridScroll = Vector2.zero; }
            tx += 12;
            Look.Outline(new Rect(tx, ty + 8, 8, 8), Look.Dust, 1.5f, 2);   // small tiles … big tiles
            int size = Mathf.RoundToInt(GUI.HorizontalSlider(new Rect(tx + 14, ty + 4, 70, 16), tileSize, SmallestTile, BiggestTile));
            Look.Outline(new Rect(tx + 90, ty + 5, 14, 14), Look.Dust, 1.5f, 3);
            if (size != tileSize) { tileSize = size; EditorPrefs.SetInt(SizePref, size); nameFits.Clear(); }
            // animated pictures: playing, or a still of their first frame (kept for every project, as the tile size is)
            var pause = new Rect(tx + 110 + 12, ty, Look.ButtonWidth(PauseLabel) - 4, 24);
            if (Look.Button(pause, new GUIContent(PauseLabel, thumbs.Paused ? "Animated pictures are paused: choose to play them"
                                                                              : "Show animated pictures as a still of their first frame"),
                            thumbs.Paused ? Look.Kind.PillOn : Look.Kind.Pill))
            {
                thumbs.Paused = !thumbs.Paused;
                EditorPrefs.SetBool(PausePref, thumbs.Paused);
                Repaint();
            }

            // the tabs: drawn a little taller than their row, the part below covered by the tiles' cave, so only
            // their top corners show rounded
            float x = Pad;
            Rect chosen = new Rect(-1, 0, 0, 0);
            var mouse = Event.current.mousePosition;
            foreach (int i in tabs)
            {
                float tw = TabWidth(i, withCounts);
                bool on = i == store, hover = !on && new Rect(x, bottom - 34, tw, 34).Contains(mouse);
                float th = on ? 34 : hover ? 32 : 30;
                var r = new Rect(x, bottom - th, tw, th);
                Look.Fill(new Rect(r.x, r.y, r.width, r.height + 12), on ? Look.Cave : hover ? Look.Stone : Look.Ledge, 10);
                Look.Outline(new Rect(r.x, r.y, r.width, r.height + 12), Look.Seam, 1, 10);
                if (on) chosen = r;
                float lx = r.x + 14;
                if (i > 0) { Look.Dot(new Vector2(lx + 4, r.center.y), Look.Store(StoreNames[i])); lx += 15; }
                var ls = Look.Style("tab", Look.Styles.Tab);
                ls.normal.textColor = on || hover ? Look.Bone : Look.Dust;
                var label = new GUIContent(TabLabel(i));
                float lw = ls.CalcSize(label).x;
                GUI.Label(new Rect(lx, r.y, lw + 2, r.height), label, ls);
                if (withCounts)
                    GUI.Label(new Rect(lx + lw + 6, r.y, tw - (lx - r.x) - lw - 6, r.height), TabCount(i), Look.Style(Look.Styles.TabCount));
                if (GUI.Button(r, GUIContent.none, GUIStyle.none) && store != i)
                {
                    store = i;
                    Filter();
                    gridScroll = Vector2.zero;
                }
                x += tw + 4;
            }
            Look.Fill(new Rect(0, bottom, w, 12), Look.Cave);
            if (chosen.x < 0) Look.Fill(new Rect(0, bottom, w, 1), Look.Seam);
            else
            {
                Look.Fill(new Rect(0, bottom, chosen.x, 1), Look.Seam);
                Look.Fill(new Rect(chosen.xMax, bottom, w - chosen.xMax, 1), Look.Seam);
            }
            return bottom + 1;
        }

        /// <summary>What's wrong with the library, if anything, in boxes above the tiles.</summary>
        float DrawNotices(float y)
        {
            if (catalog.Problem != null)
                y = Notice(y, catalog.Problem + "\nLooking in: " + catalog.Root, Look.Gold);
            else if (catalog.SealStatus == SealState.Changed)
                y = Notice(y, "catalog.json was changed by something other than Hoard, so importing is paused and store links are hidden. " +
                              "Open Hoard and choose Sync (or run Hoard.bat verify) to rebuild it.", Look.Warn);
            else if (catalog.SealStatus == SealState.Foreign)
                y = Notice(y, "catalog.json was sealed with a Hoard key this account doesn't have (Hoard on another computer, " +
                              "or an earlier Hoard install), so it can't be checked here. Opening Hoard seals it again with this " +
                              "computer's key, then choose Reload.", Look.Gold);
            if (catalog.Problem == null && catalog.LeftOut > 0)
                y = Notice(y, catalog.LeftOut + " entries in catalog.json didn't look right and were left out.", Look.Dust);
            return y;
        }

        float Notice(float y, string text, Color accent)
        {
            float w = position.width - Pad * 2;
            var s = Look.Style(Look.Styles.Wrapped);
            float th = s.CalcHeight(new GUIContent(text), w - 30);
            var box = new Rect(Pad, y + 8, w, th + 20);
            if (Event.current.type == EventType.Repaint) Look.Box("notice", Look.Ledge, Look.Seam).Draw(box, false, false, false, false);
            Look.Fill(new Rect(box.x, box.y + 8, 3, box.height - 16), accent, 1.5f);
            GUI.Label(new Rect(box.x + 16, box.y + 10, w - 30, th), text, s);
            return box.yMax;
        }

        void DrawGrid(Rect area)
        {
            // "112 things in your hoard", as the app counts them, with how many there are in all when it's filtered
            var hs = Look.Style(Look.Styles.Heading);
            string count = shown.Count.ToString("N0") + (shown.Count == 1 ? " thing in your hoard" : " things in your hoard");
            float cw = hs.CalcSize(new GUIContent(count)).x;
            GUI.Label(new Rect(area.x + Pad, area.y + 12, cw + 4, 26), count, hs);
            if (shown.Count != catalog.Assets.Count)
                GUI.Label(new Rect(area.x + Pad + cw, area.y + 12, area.width - Pad * 2 - cw, 26), " of " + catalog.Assets.Count.ToString("N0"), Look.Style(Look.Styles.HeadingDust));
            string busy = packages.Waiting > 0 ? "Checking packages: " + packages.Waiting + " to go" : loading ? "Loading..." : null;
            if (busy != null)
            {
                var bs = Look.Style("busy", Look.Styles.Small);
                bs.alignment = TextAnchor.MiddleRight;
                GUI.Label(new Rect(area.x + Pad, area.y + 40, area.width - Pad * 2, 16), busy, bs);
            }
            var view = new Rect(area.x, area.y + 46, area.width, Mathf.Max(0, area.height - 46));
            if (shown.Count == 0)
            {
                bool filtered = search.Length > 0 || store > 0 || inProjectOnly || updatesOnly || (packagesOnly && catalog.Assets.Count > 0);
                if (catalog.Problem != null)
                    DrawEmpty(view, "Hoard's library isn't here", "Open the Hoard app and choose Sync, or choose Folder... to show Hoard for Unity where Hoard's downloads are.", false);
                else if (catalog.Assets.Count == 0)
                    DrawEmpty(view, "Nothing in your hoard yet", "Download something with the Hoard app, then choose Reload.", false);
                else
                    DrawEmpty(view, "Nothing here", filtered ? "Try another store, or clear the search and the filters." : "", filtered);
                return;
            }
            float inner = view.width - Pad * 2 - 14;   // (room for the scroll bar)
            int cols = Mathf.Max(1, Mathf.FloorToInt((inner + Gap) / (tileSize + Gap)));
            // tiles share out the row as the app's do, but no bigger than a third over the size chosen (one column in a
            // narrow window would otherwise be as wide as the window)
            float tw = Mathf.Floor(Mathf.Min((inner - Gap * (cols - 1)) / cols, tileSize * 1.33f));
            var ns = Look.Style("name", Look.Styles.Name);
            float rowH = tw + 8 + ns.lineHeight * 2 + 4 + 16 + 20;
            int rows = (shown.Count + cols - 1) / cols;
            gridView = view;
            gridColumns = cols;
            gridRow = rowH;
            var content = new Rect(0, 0, view.width - 14, Pad + rows * rowH);
            gridScroll = GUI.BeginScrollView(view, gridScroll, content, false, false);
            int first, last;   // only the rows on screen are drawn, however many there are
            ListView.VisibleRange(gridScroll.y - Pad, view.height, rowH, rows, out first, out last);
            for (int r = first; r <= last; r++)
                for (int c = 0; c < cols; c++)
                {
                    int i = r * cols + c;
                    if (i >= shown.Count) break;
                    DrawTile(shown[i], new Rect(Pad + c * (tw + Gap), Pad / 2 + r * rowH, tw, rowH - 20));
                }
            GUI.EndScrollView();
        }

        /// <summary>A product as the app's tiles show it: its picture with its store's colour along the foot and badges
        /// for what's in this project, its name (two lines at most) and its creator. Choosing it shows its details.</summary>
        void DrawTile(HoardAsset a, Rect slot)
        {
            var e = Event.current;
            // (a tile scrolled part way out of sight is only under the pointer where it shows)
            bool inView = e.mousePosition.y >= gridScroll.y && e.mousePosition.y <= gridScroll.y + gridView.height;
            bool hover = inView && slot.Contains(e.mousePosition), chosen = a == selected;
            var art = new Rect(slot.x, slot.y + (hover ? 0 : 3), slot.width, slot.width);   // lifts on hover
            if (chosen) Look.Outline(new Rect(art.x - 5, art.y - 5, art.width + 10, art.height + 10), Look.Gold, 3, 16);
            Look.Art(art, thumbs.Get(a.ThumbPath), a.Store, a.Name);

            var s = ProjectStatus(a);
            float by = art.y + 7;
            if (s >= InProject.Partly)
            {
                string mark = s == InProject.Yes ? "In this project" : "Partly in project";
                if (Look.BadgeWidth(mark) > art.width - 14) mark = s == InProject.Yes ? "In project" : "Partly";
                Look.Badge(new Vector2(art.x + 7, by), mark, false);
                by += 22;
                string upd = NewerDownload(a) != null ? "Update to import" : UpdateInHoard(a) > 0 ? "Update in Hoard" : null;
                if (upd != null)
                {
                    bool gold = upd == "Update to import";   // to import here: gold, as the app's updates are
                    if (Look.BadgeWidth(upd) > art.width - 14) upd = "Update";
                    Look.Badge(new Vector2(art.x + 7, by), upd, gold);
                }
            }

            var ns = Look.Style("name", Look.Styles.Name);
            ns.normal.textColor = chosen ? Look.GoldText : Look.Bone;
            string name = NameFit(a, slot.width, ns);
            float nameH = ns.CalcHeight(new GUIContent(name), slot.width);
            float ny = slot.y + 3 + slot.width + 8;
            GUI.Label(new Rect(slot.x, ny, slot.width, nameH), name, ns);
            FittedLabel(new Rect(slot.x, ny + nameH, slot.width, 16), a.Creator, Look.Style(Look.Styles.Small));
            GUI.Label(slot, new GUIContent("", a.Name + "\n" + a.Creator + "  ·  " + HoardCatalog.StoreLabel(a.Store)), GUIStyle.none);
            if (e.type == EventType.MouseDown && e.button == 0 && hover)
            {
                Select(a, false);
                e.Use();
            }
        }

        /// <summary>A product's name cut to two lines with "…", worked out once for each tile width.</summary>
        string NameFit(HoardAsset a, float width, GUIStyle style)
        {
            KeyValuePair<float, string> known;
            if (nameFits.TryGetValue(a, out known) && known.Key == width) return known.Value;
            float twoLines = style.CalcHeight(new GUIContent("Ag\nAg"), width) + 1;
            string fit = TextFit.Fit(a.Name, 1, t => style.CalcHeight(new GUIContent(t), width) <= twoLines ? 0 : 2);
            if (nameFits.Count > 4000) nameFits.Clear();
            nameFits[a] = new KeyValuePair<float, string>(width, fit);
            return fit;
        }

        void DrawEmpty(Rect area, string title, string hint, bool clear)
        {
            var ts = Look.Style("emptyTitle", Look.Styles.Heading);
            ts.alignment = TextAnchor.MiddleCenter;
            float w = Mathf.Min(area.width - Pad * 2, 420), x = area.x + (area.width - w) / 2, y = area.y + Mathf.Min(80, area.height / 4);
            GUI.Label(new Rect(x, y, w, 30), title, ts);
            var hs = Look.Style(Look.Styles.Centered);
            float hh = hint.Length > 0 ? hs.CalcHeight(new GUIContent(hint), w) : 0;
            GUI.Label(new Rect(x, y + 36, w, hh), hint, hs);
            if (clear)
            {
                float bw = Look.ButtonWidth("Clear the filters");
                if (Look.Button(new Rect(x + (w - bw) / 2, y + 48 + hh, bw, Look.ButtonHeight), "Clear the filters"))
                {
                    search = "";
                    store = 0;
                    inProjectOnly = updatesOnly = false;
                    GUI.FocusControl(null);
                    Filter();
                }
            }
        }

        /// <summary>The chosen product, beside the tiles as the app's panel: its picture, name, creator and store, its
        /// files with Import, and its folder and store page.</summary>
        void DrawDetails(Rect area)
        {
            var a = selected;
            Look.Fill(area, Look.Ledge);
            Look.Fill(new Rect(area.x, area.y, 1, area.height), Look.Seam);
            if (Look.Button(new Rect(area.xMax - 16 - 28, area.y + 12, 28, Look.ButtonHeight), new GUIContent("×", "Close (Esc)"), Look.Kind.Ghost))
            {
                selected = null;
                GUIUtility.ExitGUI();
            }
            GUILayout.BeginArea(new Rect(area.x + 1, area.y + 12, area.width - 1, area.height - 12));
            detailScroll = GUILayout.BeginScrollView(detailScroll, false, false, GUIStyle.none, GUI.skin.verticalScrollbar);   // never sideways
            GUILayout.BeginHorizontal();
            GUILayout.Space(18);
            GUILayout.BeginVertical();
            float width = area.width - 1 - 36 - 14;

            float side = Mathf.Min(width - 40, 240);
            var pic = GUILayoutUtility.GetRect(side, side, GUILayout.Width(side), GUILayout.Height(side));
            Look.Art(pic, thumbs.Get(a.ThumbPath), a.Store, a.Name, 14);
            if (filesFor != a)   // the chosen product's files are looked up once, not on every repaint
            {
                filesFor = a;
                files = new List<KeyValuePair<string, string>>();
                foreach (string f in a.Files)
                {
                    string path = catalog.FilePath(a, f);
                    files.Add(new KeyValuePair<string, string>(f, path));
                    if (path != null && f.EndsWith(".zip", StringComparison.OrdinalIgnoreCase))   // the packages it came zipped in
                        foreach (string p in a.PackagePaths)
                            if (PackageFile.IsZipped(p) && PackageFile.OnDisk(p) == path)
                                files.Add(new KeyValuePair<string, string>(PackageFile.Label(p), p));
                }
            }
            GUILayout.Space(12);
            GUILayout.Label(a.Name, Look.Style(Look.Styles.Title), GUILayout.Width(width));
            GUILayout.Label("by " + a.Creator, Look.Style("by", Look.Styles.Wrapped), GUILayout.Width(width));
            StorePill(a.Store);
            if (a.Variants != null) GUILayout.Label(a.Variants, Look.Style("variants", Look.Styles.Dust), GUILayout.Width(width));
            if (a.Note != null) GUILayout.Label("For " + a.Note, Look.Style("note", Look.Styles.Dust), GUILayout.Width(width));
            if (a.Tags.Count > 0)
            {
                GUILayout.Space(4);
                GUILayout.Label("#" + string.Join("   #", a.Tags.ToArray()), Look.Style("tags", Look.Styles.Name), GUILayout.Width(width));
            }
            GUILayout.Space(10);

            bool paused = catalog.SealStatus == SealState.Changed || PendingImport.Active || EditorApplication.isCompiling;
            string newer = NewerDownload(a);
            int waiting = UpdateInHoard(a);
            if (newer != null)
            {
                GUILayout.BeginVertical(Look.Box("update", Look.Alpha(Look.Gold, 0.16f), Look.Alpha(Look.Gold, 0.6f)), GUILayout.Width(width));
                GUILayout.Label("A newer download than the one in this project: " + PackageFile.Label(newer) + ".", Look.Style(Look.Styles.Wrapped));
                GUILayout.Space(6);
                EditorGUI.BeginDisabledGroup(paused);
                if (Look.LayoutButton("Import update", Look.Kind.Primary)) Import(a, newer);
                EditorGUI.EndDisabledGroup();
                GUILayout.EndVertical();
            }
            else if (waiting > 0)
            {
                GUILayout.BeginVertical(Look.Box("waiting", Look.Cave, Look.Seam), GUILayout.Width(width));
                GUILayout.Label("The creator updated this product (" + waiting + (waiting == 1 ? " new or changed file" : " new or changed files") +
                                "). Download the update in Hoard (Downloads, Updates), then import it here.", Look.Style(Look.Styles.Wrapped));
                GUILayout.EndVertical();
            }

            GUILayout.Space(6);
            GUILayout.Label("Files", Look.Style(Look.Styles.Section));
            float inner = width - 24;   // inside a file's box
            var body = Look.Style(Look.Styles.Body);
            foreach (var entry in files)
            {
                string file = entry.Key, path = entry.Value;
                GUILayout.BeginVertical(Look.Box("file", Look.Cave, Look.Seam), GUILayout.Width(width));
                bool package = path != null && HoardCatalog.IsUnityPackage(file);
                float showW = Look.ButtonWidth("Show");
                if (!package)   // one line: the name, and Show
                {
                    GUILayout.BeginHorizontal();
                    // the name takes the room the button leaves, cut in the middle if it must be
                    // ("CyclopsBe….unitypackage"), never wrapped part way through a word; the whole name is its tooltip
                    float nameW = path == null ? inner : inner - showW - 8;
                    FittedLabel(GUILayoutUtility.GetRect(nameW, Look.ButtonHeight, GUILayout.Width(nameW), GUILayout.Height(Look.ButtonHeight)), file, body, true);
                    if (path != null)
                    {
                        GUILayout.Space(8);
                        if (Look.LayoutButton("Show", Look.Kind.Ghost, "Show the file in its folder")) EditorUtility.RevealInFinder(path);
                    }
                    GUILayout.EndHorizontal();
                    if (path == null) GUILayout.Label("Missing from Hoard's folder", Look.Style(Look.Styles.Small));
                    GUILayout.EndVertical();
                    continue;
                }
                FittedLabel(GUILayoutUtility.GetRect(inner, 20, GUILayout.Width(inner), GUILayout.Height(20)), file, body, true);
                int have, total;
                var st = packages.Status(path, out have, out total);
                string importLabel = st == InProject.Yes ? "Import again" : "Import";
                float buttonsW = Look.ButtonWidth(importLabel) + 6 + (have > 0 ? Look.ButtonWidth("Select") + 6 : 0) + showW;
                var small = Look.Style("here", Look.Styles.Small);
                string here = st != InProject.Unknown ? have + " of " + total + " here" : "";
                float hereW = here.Length > 0 ? small.CalcSize(new GUIContent(here)).x + 8 : 0;
                bool oneRow = hereW + buttonsW <= inner;   // else the count goes above the buttons
                if (!oneRow && here.Length > 0) GUILayout.Label(here, small, GUILayout.Width(inner));
                GUILayout.Space(4);
                GUILayout.BeginHorizontal(GUILayout.Width(inner));
                if (oneRow && here.Length > 0) GUILayout.Label(here, small, GUILayout.Width(hereW), GUILayout.Height(Look.ButtonHeight));
                GUILayout.FlexibleSpace();
                EditorGUI.BeginDisabledGroup(paused);
                if (Look.LayoutButton(importLabel, st == InProject.Yes ? Look.Kind.Ghost : Look.Kind.Primary)) Import(a, path);
                EditorGUI.EndDisabledGroup();
                GUILayout.Space(6);
                if (have > 0)
                {
                    if (Look.LayoutButton("Select", Look.Kind.Ghost, "Select its files in the Project window")) SelectInProject(path);
                    GUILayout.Space(6);
                }
                if (Look.LayoutButton("Show", Look.Kind.Ghost, PackageFile.IsZipped(path) ? "Show the .zip it's in, in its folder" : "Show the file in its folder"))
                    EditorUtility.RevealInFinder(PackageFile.OnDisk(path));
                GUILayout.EndHorizontal();
                GUILayout.EndVertical();
            }
            GUILayout.Space(10);
            GUILayout.BeginHorizontal();
            string folder = catalog.FolderPath(a);
            if (folder != null && Look.LayoutButton("Open folder")) EditorUtility.RevealInFinder(folder);
            if (folder != null) GUILayout.Space(6);
            if (HoardCatalog.StoreLink(a.Store, a.Url) && Look.LayoutButton("Store page", Look.Kind.Ghost, a.Url)) Application.OpenURL(a.Url);
            GUILayout.EndHorizontal();
            GUILayout.Space(18);
            GUILayout.EndVertical();
            GUILayout.Space(18);
            GUILayout.EndHorizontal();
            GUILayout.EndScrollView();
            GUILayout.EndArea();
        }

        /// <summary>The store as the app shows it on a product: its diamond and its name, in a pill.</summary>
        static void StorePill(string store)
        {
            string label = HoardCatalog.StoreLabel(store);
            var s = Look.Style("pill", Look.Styles.Tab);
            s.normal.textColor = Look.Bone;
            float w = s.CalcSize(new GUIContent(label)).x + 34;
            var r = GUILayoutUtility.GetRect(w, 24, GUILayout.Width(w), GUILayout.Height(24));
            r.y += 2;
            Look.Fill(r, Look.Cave, 12);
            Look.Outline(r, Look.Seam, 1, 12);
            Look.Dot(new Vector2(r.x + 13, r.center.y), Look.Store(store));
            GUI.Label(new Rect(r.x + 23, r.y, w - 26, r.height), label, s);
            GUILayout.Space(2);
        }

        /// <summary>The keys the app's library has: / to search, Esc to close the details (or leave the search), and the
        /// arrows to move between tiles.</summary>
        void Keys()
        {
            var e = Event.current;
            if (e.type != EventType.KeyDown) return;
            bool typing = EditorGUIUtility.editingTextField;
            if (!typing && e.character == '/')
            {
                EditorGUI.FocusTextInControl(SearchControl);
                e.Use();
                return;
            }
            if (e.keyCode == KeyCode.Escape)
            {
                if (typing) GUI.FocusControl(null);
                else if (selected != null) selected = null;
                else return;
                e.Use();
                Repaint();
                return;
            }
            if (typing || shown.Count == 0) return;
            int step = e.keyCode == KeyCode.LeftArrow ? -1 : e.keyCode == KeyCode.RightArrow ? 1
                     : e.keyCode == KeyCode.UpArrow ? -gridColumns : e.keyCode == KeyCode.DownArrow ? gridColumns : 0;
            if (step == 0) return;
            int at = selected == null ? -1 : shown.IndexOf(selected);
            Select(shown[at < 0 ? 0 : Mathf.Clamp(at + step, 0, shown.Count - 1)], true);
            e.Use();
        }

        /// <summary>A label cut with "…" to fit its rectangle (TextFit), with the whole text as its tooltip when it's cut.</summary>
        static void FittedLabel(Rect r, string text, GUIStyle style, bool middle = false)
        {
            string shown = TextFit.Fit(text, r.width, t => style.CalcSize(new GUIContent(t)).x, middle);
            GUI.Label(r, new GUIContent(shown, shown == text ? null : text), style);
        }

        void Import(HoardAsset a, string path)
        {
            string file;
            try
            {
                // a package in a .zip is unpacked first, into the project's Library folder (never into Assets)
                if (PackageFile.IsZipped(path)) EditorUtility.DisplayProgressBar("Hoard", "Unpacking " + PackageFile.Name(path) + " from its .zip", 0.5f);
                file = PackageFile.ForImport(path, Path.Combine("Library", "Hoard", "Unzipped"));
            }
            catch (Exception e)
            {
                EditorUtility.DisplayDialog("Hoard", PackageFile.Name(path) + " couldn't be unpacked from its .zip (" + e.Message + ").", "OK");
                return;
            }
            finally { EditorUtility.ClearProgressBar(); }
            PendingImport.Start(a, file);
            AssetDatabase.ImportPackage(file, true);   // Unity's own dialog: you choose what comes in
        }

        /// <summary>The same folder, however it's written: the folder picker gives "C:/Users/..." where Hoard's own
        /// is "C:\Users\...", and Windows doesn't mind case.</summary>
        static bool SamePath(string a, string b)
        {
            if (string.IsNullOrEmpty(a) || string.IsNullOrEmpty(b)) return false;
            try
            {
                Func<string, string> plain = p => Path.GetFullPath(p).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
                return string.Equals(plain(a), plain(b), Application.platform == RuntimePlatform.WindowsEditor || Application.platform == RuntimePlatform.OSXEditor
                    ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal);
            }
            catch (Exception) { return a == b; }
        }

        void SelectInProject(string packagePath)
        {
            var found = new List<UnityEngine.Object>();
            foreach (string g in packages.Guids(packagePath))
            {
                string p = AssetDatabase.GUIDToAssetPath(g);
                if (!ProjectShare.InAssets(p)) continue;   // another package's copy under Packages/ isn't this product's
                var o = AssetDatabase.LoadMainAssetAtPath(p);
                if (o != null && !AssetDatabase.IsValidFolder(p)) found.Add(o);
            }
            Selection.objects = found.ToArray();
            if (found.Count > 0) EditorGUIUtility.PingObject(found[0]);
        }
    }
}
