// Hoard's Credits window (issue #51): the creators of the assets this project uses, ready to paste where you share
// your avatar or world. Opened from the Create Credits List button in Window > Hoard. What you change (entries added by hand,
// ones left out, the title and style) is kept in ProjectSettings/Hoard/credits.json, so it travels with the project.
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
            EditorApplication.projectChanged += Refresh;
        }

        void OnDisable() { EditorApplication.projectChanged -= Refresh; }

        void OnFocus() { Refresh(); }

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

        void Changed()
        {
            try { settings.Save(SettingsFile); }
            catch (IOException e) { Debug.LogWarning("Hoard: couldn't save the credits settings: " + e.Message); }
            Remake();
            if (source != null) source.ReportSoon();   // Hoard's Projects view shows the same credits
        }

        void OnGUI()
        {
            if (source == null)
            {
                EditorGUILayout.HelpBox("Open Window > Hoard: the credits list is made from what it finds in this project.", MessageType.Info);
                if (GUILayout.Button("Open Hoard")) { HoardWindow.Open(); Refresh(); }
                return;
            }
            if (!ready) EditorGUILayout.HelpBox("Hoard is still loading your library.", MessageType.Info);
            else if (stillChecking > 0)
                EditorGUILayout.HelpBox("Still checking " + stillChecking + " packages, so the list may grow. Choose Refresh in a moment.", MessageType.Info);

            EditorGUI.BeginChangeCheck();
            settings.Title = Credits.OneLine(EditorGUILayout.TextField("Title", settings.Title), 100);
            settings.Format = (CreditFormat)EditorGUILayout.Popup("Style", (int)settings.Format, Credits.FormatNames);
            if (EditorGUI.EndChangeCheck()) Changed();

            int included = all.FindAll(e => !settings.LeftOut.Contains(e.Key)).Count;
            EditorGUILayout.BeginHorizontal();
            GUILayout.Label(included + " of " + all.Count + " in the list. Untick any you don't want credited.", EditorStyles.miniLabel);
            GUILayout.FlexibleSpace();
            if (GUILayout.Button("Refresh", GUILayout.Width(70))) Refresh();
            EditorGUILayout.EndHorizontal();

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
                if (e.Added && GUILayout.Button("Remove", EditorStyles.miniButton, GUILayout.Width(60))) remove = e;
                EditorGUILayout.EndHorizontal();
            }
            if (all.Count == 0)
                GUILayout.Label("Nothing from Hoard is in this project yet. Import something from Window > Hoard, or add an asset by hand.",
                                EditorStyles.wordWrappedMiniLabel);
            EditorGUILayout.EndScrollView();
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
                if (badLink) EditorGUILayout.HelpBox("A link must be a plain https:// address.", MessageType.None);
                EditorGUI.BeginDisabledGroup(name.Length == 0 || badLink || settings.Added.Count >= CreditsFile.MaxAdded);
                if (GUILayout.Button("Add", GUILayout.Width(80)))
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

            GUILayout.Label("Preview", EditorStyles.boldLabel);
            textScroll = EditorGUILayout.BeginScrollView(textScroll, GUILayout.ExpandHeight(true));
            EditorGUILayout.SelectableLabel(text, EditorStyles.textArea, GUILayout.ExpandHeight(true),
                                            GUILayout.MinHeight(EditorStyles.textArea.CalcHeight(new GUIContent(text), position.width - 30)));
            EditorGUILayout.EndScrollView();

            EditorGUILayout.BeginHorizontal();
            if (GUILayout.Button("Copy", GUILayout.Width(90)))
            {
                EditorGUIUtility.systemCopyBuffer = text;
                ShowNotification(new GUIContent("Copied"));
            }
            if (GUILayout.Button("Save as...", GUILayout.Width(90))) SaveAs();
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
