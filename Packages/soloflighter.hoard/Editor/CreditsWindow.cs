// Hoard's Credits window (issue #51): the creators of the assets this project uses, ready to paste where you share
// your avatar or world. Opened from Create Credits List in the Hoard window, or Hoard › Create Credits List. What
// you change (entries added by hand, ones left out, the title and style) is kept in ProjectSettings/Hoard/credits.json,
// so it travels with the project.
using System.Collections.Generic;
using System.IO;
using System.Text;
using UnityEditor;
using UnityEngine;

namespace SoloFlighter.Hoard.Editor
{
    public sealed class CreditsWindow : EditorWindow
    {
        public static readonly string SettingsFile = Path.Combine("ProjectSettings", "Hoard", "credits.json");

        HoardWindow source;
        CreditsFile settings;
        List<CreditEntry> all = new List<CreditEntry>();   // everything found or added, left-out ones included
        string text = "";
        int stillChecking;
        bool ready;
        Vector2 listScroll, textScroll;
        bool adding;
        string newName = "", newCreator = "", newUrl = "";
        string listTitle;          // the title as you're typing it (a space at the end stays while you type)
        double saveAt = -1;        // typing saves once you pause, not on every key

        public static void Open(HoardWindow from)
        {
            var w = GetWindow<CreditsWindow>(true, "Create Credits List");
            w.minSize = new Vector2(460, 420);
            w.source = from;
            w.Refresh();
            w.Show();
        }

        void OnEnable()
        {
            settings = CreditsFile.Load(SettingsFile);
            listTitle = settings.Title;
            EditorApplication.projectChanged += OnProjectChanged;
            EditorApplication.update += SaveWhenDue;
        }

        void OnDisable()
        {
            EditorApplication.projectChanged -= OnProjectChanged;
            EditorApplication.update -= SaveWhenDue;
            if (saveAt >= 0) Save();
        }

        void SaveWhenDue() { if (saveAt >= 0 && EditorApplication.timeSinceStartup >= saveAt) Save(); }

        void OnFocus() { Refresh(); }

        void OnProjectChanged() { if (ProjectWatch.LastChangeCounts()) Refresh(); }

        void Refresh()
        {
            if (source == null)
            {
                var open = Resources.FindObjectsOfTypeAll<HoardWindow>();
                if (open.Length > 0) source = open[0];
            }
            var found = source != null ? source.UsedInProject(out stillChecking, out ready) : new List<CreditEntry>();
            if (source == null) { stillChecking = 0; ready = false; }
            found.AddRange(settings.Added);
            all = Credits.Build(found, null);
            Remake();
            Repaint();
        }

        void Remake()
        {
            text = Credits.Format(Credits.Build(all, settings.LeftOut), settings.Format, settings.Title);
        }

        void Changed(bool typing = false)
        {
            Remake();
            if (typing) { saveAt = EditorApplication.timeSinceStartup + 1; return; }
            Save();
        }

        void Save()
        {
            saveAt = -1;
            try { settings.Save(SettingsFile); }   // (read-only, say: said, never thrown out of drawing the window)
            catch (System.Exception e) when (e is IOException || e is System.UnauthorizedAccessException)
            {
                Debug.LogWarning("Hoard: couldn't save the credits settings: " + e.Message);
            }
            if (source != null) source.ReportSoon();   // Hoard's Projects view shows the same credits
        }

        // In the app's look, as the Hoard window is (Look.cs): its colours, its buttons, its boxes.
        void OnGUI()
        {
            if (Event.current.type == EventType.MouseMove) Repaint();
            Look.Fill(new Rect(0, 0, position.width, position.height), Look.Cave);
            GUILayout.BeginHorizontal();
            GUILayout.Space(16);
            GUILayout.BeginVertical();
            GUILayout.Space(14);
            GUILayout.Label("Credits list", Look.Style(Look.Styles.Heading));
            GUILayout.Label("The creators of the Hoard products in this project, to credit them where you share it.", Look.Style("intro", Look.Styles.Dust));
            GUILayout.Space(8);
            Body();
            GUILayout.Space(14);
            GUILayout.EndVertical();
            GUILayout.Space(16);
            GUILayout.EndHorizontal();
        }

        static void Note(string text)
        {
            GUILayout.BeginVertical(Look.Box("note", Look.Ledge, Look.Seam));
            GUILayout.Label(text, Look.Style(Look.Styles.Wrapped));
            GUILayout.EndVertical();
        }

        void Body()
        {
            wantsMouseMove = true;
            if (source == null)
            {
                Note("Open Hoard (Hoard › Open Hoard): the credits list is made from what it finds in this project.");
                if (Look.LayoutButton("Open Hoard", Look.Kind.Primary)) { HoardWindow.Open(); Refresh(); }
                return;
            }
            if (!ready) Note("Hoard is still loading your library.");
            else if (stillChecking > 0)
                Note("Still checking " + stillChecking + " packages, so the list may grow. Choose Refresh in a moment.");

            EditorGUI.BeginChangeCheck();
            listTitle = EditorGUILayout.TextField("Title", listTitle ?? "");
            if (EditorGUI.EndChangeCheck())
            {
                settings.Title = Credits.OneLine(listTitle, 100);
                Changed(true);
            }
            EditorGUI.BeginChangeCheck();
            settings.Format = (CreditFormat)EditorGUILayout.Popup("Style", (int)settings.Format, Credits.FormatNames);
            if (EditorGUI.EndChangeCheck()) Changed();

            int included = all.FindAll(e => !settings.LeftOut.Contains(e.Key)).Count;
            EditorGUILayout.BeginHorizontal();
            GUILayout.Label(included + " of " + all.Count + " in the list. Untick any you don't want credited.", Look.Style(Look.Styles.Small), GUILayout.Height(Look.ButtonHeight));
            GUILayout.FlexibleSpace();
            if (Look.LayoutButton("Refresh")) Refresh();
            EditorGUILayout.EndHorizontal();

            GUILayout.BeginVertical(Look.Box("list", Look.Ledge, Look.Seam, 10, 10, 6));
            listScroll = EditorGUILayout.BeginScrollView(listScroll, GUILayout.MinHeight(120), GUILayout.MaxHeight(260));
            CreditEntry remove = null;
            foreach (var e in all)
            {
                EditorGUILayout.BeginHorizontal();
                bool on = !settings.LeftOut.Contains(e.Key);
                string label = e.Name + "  ·  " + (e.Creator.Length > 0 ? e.Creator : "Unknown creator") +
                               (e.Added ? "  ·  added by hand" : e.Store.Length > 0 ? "  ·  " + HoardCatalog.StoreLabel(e.Store) : "");
                bool now = EditorGUILayout.ToggleLeft(label, on);
                if (now != on)
                {
                    if (now) settings.LeftOut.Remove(e.Key); else settings.LeftOut.Add(e.Key);
                    Changed();
                }
                if (e.Added && Look.LayoutButton("Remove")) remove = e;
                EditorGUILayout.EndHorizontal();
            }
            if (all.Count == 0)
                GUILayout.Label("Nothing from Hoard is in this project yet. Import something from Hoard › Open Hoard, or add an asset by hand.",
                                Look.Style("nothing", Look.Styles.Centered));
            EditorGUILayout.EndScrollView();
            GUILayout.EndVertical();
            if (remove != null)
            {
                settings.Added.RemoveAll(a => a.Key == remove.Key);
                settings.LeftOut.Remove(remove.Key);
                Changed();
                Refresh();
            }

            adding = EditorGUILayout.Foldout(adding, "Add an asset by hand (one that didn't come through Hoard)", true);
            if (adding)
            {
                EditorGUI.indentLevel++;
                newName = EditorGUILayout.TextField("Name", newName);
                newCreator = EditorGUILayout.TextField("Creator", newCreator);
                newUrl = EditorGUILayout.TextField("Link (optional)", newUrl);
                string name = Credits.OneLine(newName, 300), url = newUrl.Trim();
                bool badLink = url.Length > 0 && Credits.Link(null, url, true) == null;
                if (badLink) Note("A link must be a plain https:// address.");
                EditorGUI.BeginDisabledGroup(name.Length == 0 || badLink || settings.Added.Count >= CreditsFile.MaxAdded);
                if (Look.LayoutButton("Add", Look.Kind.Primary))
                {
                    var e = new CreditEntry { Store = "", Name = name, Creator = Credits.OneLine(newCreator, 200), Added = true,
                                              Url = url.Length > 0 ? Credits.Link(null, url, true) : null };
                    settings.Added.RemoveAll(a => a.Key == e.Key);
                    settings.Added.Add(e);
                    newName = newCreator = newUrl = "";
                    GUI.FocusControl(null);
                    Changed();
                    Refresh();
                }
                EditorGUI.EndDisabledGroup();
                EditorGUI.indentLevel--;
            }

            GUILayout.Space(6);
            GUILayout.Label("Preview", Look.Style(Look.Styles.Section));
            textScroll = EditorGUILayout.BeginScrollView(textScroll, GUILayout.ExpandHeight(true));
            EditorGUILayout.SelectableLabel(text, EditorStyles.textArea, GUILayout.ExpandHeight(true),
                                            GUILayout.MinHeight(EditorStyles.textArea.CalcHeight(new GUIContent(text), position.width - 30)));
            EditorGUILayout.EndScrollView();

            EditorGUILayout.BeginHorizontal();
            if (Look.LayoutButton("Copy", Look.Kind.Primary))
            {
                EditorGUIUtility.systemCopyBuffer = text;
                ShowNotification(new GUIContent("Copied"));
            }
            if (Look.LayoutButton("Save as...")) SaveAs();
            EditorGUILayout.EndHorizontal();
        }

        void SaveAs()
        {
            string ext = settings.Format == CreditFormat.Markdown ? "md" : "txt";
            // The project's own folder, not Assets: a text file there is never part of an upload.
            string path = EditorUtility.SaveFilePanel("Save the credits list", Directory.GetCurrentDirectory(), "Credits." + ext, ext);
            if (string.IsNullOrEmpty(path)) return;
            try
            {
                File.WriteAllText(path, text, new UTF8Encoding(false));
                ShowNotification(new GUIContent("Saved"));
                if (Path.GetFullPath(path).StartsWith(Path.GetFullPath("Assets") + Path.DirectorySeparatorChar)) AssetDatabase.Refresh();
            }
            catch (IOException e) { EditorUtility.DisplayDialog("Hoard", "Couldn't save the credits list: " + e.Message, "OK"); }
            catch (System.UnauthorizedAccessException e) { EditorUtility.DisplayDialog("Hoard", "Couldn't save the credits list: " + e.Message, "OK"); }
        }
    }
}
