// Checks for the Unity package's plain-C# core, run by tests/test_unity.py against material Hoard's own Python
// code made (sealed catalogs, canonical JSON, a Unity package). Prints PASS or FAIL lines.
using System;
using System.Collections.Generic;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using SoloFlighter.Hoard;

public static class CoreTests
{
    static int failures;

    // GIF pictures (animated thumbnails): every frame as Chromium shows it (tests/unity/gifs, made by
    // make_gif_fixtures.py), shrunk to thumbnail size the right way up, and damaged files never throwing
    static void GifChecks(string gifs)
    {
        var expected = Json.Parse(File.ReadAllText(Path.Combine(gifs, "expected.json"), Encoding.UTF8));
        foreach (var file in expected.Members)
        {
            var img = GifDecoder.Decode(File.ReadAllBytes(Path.Combine(gifs, file.Key)), 4096);
            var want = file.Value.Items;
            Check("gif " + file.Key + ": decoded", img != null);
            if (img == null) continue;
            Check("gif " + file.Key + ": every frame", img.Frames.Count == want.Count, img.Frames.Count + " of " + want.Count);
            for (int i = 0; i < Math.Min(want.Count, img.Frames.Count); i++)
            {
                var w = want[i];
                long ms = w.Long("ms") ?? 0;
                Check("gif " + file.Key + " frame " + i + ": size", img.Width == w.Long("width") && img.Height == w.Long("height"),
                      img.Width + "x" + img.Height);
                Check("gif " + file.Key + " frame " + i + ": as Chromium shows it", Sha(TopDown(img.Frames[i], img.Width, img.Height)) == w.Str("sha256"));
                Check("gif " + file.Key + " frame " + i + ": delay", img.DelaysMs[i] == (ms < 20 ? 100 : ms), img.DelaysMs[i] + " ms");
            }
        }

        byte[] anim = File.ReadAllBytes(Path.Combine(gifs, "anim.gif"));
        var small = GifDecoder.Decode(anim, 20);
        Check("gif: shrunk to fit, keeping its shape", small != null && small.Width == 20 && small.Height == 15, small == null ? "null" : small.Width + "x" + small.Height);
        var full = GifDecoder.Decode(anim, 4096);
        // anim.gif's first frame: red wherever it's drawn, from column 1; its top-left pixel is transparent
        var top = TopDown(full.Frames[0], full.Width, full.Height);
        Check("gif: rows from the bottom, as Unity's textures are", full.Frames[0][((full.Height - 1) * full.Width + 1) * 4] == top[1 * 4]
              && top[1 * 4] == 255 && top[3] == 0);
        Check("gif: which frame shows when", full.FrameAt(0) == 0 && full.FrameAt(99) == 0 && full.FrameAt(100) == 1 &&
              full.FrameAt(149) == 1 && full.FrameAt(150) == 2 && full.FrameAt(449) == 2 && full.FrameAt(450) == 0);

        var cut = new byte[anim.Length / 2];
        Array.Copy(anim, cut, cut.Length);
        var partial = GifDecoder.Decode(cut);
        Check("gif: a file cut short gives what could be read", partial != null && partial.Frames.Count >= 1);
        Check("gif: not a GIF", GifDecoder.Decode(Encoding.ASCII.GetBytes("PNG pretending")) == null && GifDecoder.Decode(new byte[0]) == null &&
              GifDecoder.Decode(null) == null);
        var huge = (byte[])anim.Clone();
        huge[6] = 0xFF; huge[7] = 0xFF;   // 65535 pixels wide
        Check("gif: a canvas too big to be a thumbnail is refused", GifDecoder.Decode(huge) == null);
        var rnd = new Random(51);
        bool threw = false;
        for (int n = 0; n < 300; n++)   // damaged anywhere: never throws, never hangs
        {
            var bad = (byte[])anim.Clone();
            for (int k = 0; k < 8; k++) bad[6 + rnd.Next(bad.Length - 6)] = (byte)rnd.Next(256);
            try { GifDecoder.Decode(bad); } catch (Exception) { threw = true; }
        }
        Check("gif: damaged files don't throw", !threw);
    }

    // which picture the window shows: a GIF thumbnail now; for a WebP one (which Unity can't show), a preview
    // among the product's files, as Hoard's own pages choose
    static void PictureChecks(string gifs)
    {
        string root = Path.Combine(Path.GetTempPath(), "hoard-pictures-" + Guid.NewGuid().ToString("N"));
        string a = Path.Combine(root, "Booth", "Kitsu", "Animated"), b = Path.Combine(root, "Booth", "Kitsu", "Webp"),
               c = Path.Combine(root, "Booth", "Kitsu", "Plain");
        foreach (string d in new[] { a, b, c }) Directory.CreateDirectory(d);
        File.Copy(Path.Combine(gifs, "anim.gif"), Path.Combine(a, "_thumbnail.gif"));
        File.WriteAllBytes(Path.Combine(b, "_thumbnail.webp"), new byte[] { 1 });
        File.WriteAllBytes(Path.Combine(b, "readme.png"), new byte[] { 1 });
        File.Copy(Path.Combine(gifs, "anim.gif"), Path.Combine(b, "Preview.gif"));
        File.WriteAllBytes(Path.Combine(c, "texture.webp"), new byte[] { 1 });
        File.WriteAllText(Path.Combine(root, "catalog.json"),
            "{\"format\":\"hoard-catalog\",\"version\":3,\"assets\":[" +
            "{\"store\":\"Booth\",\"name\":\"Animated\",\"creator\":\"Kitsu\",\"folder\":\"Booth/Kitsu/Animated\",\"files\":[]}," +
            "{\"store\":\"Booth\",\"name\":\"Webp\",\"creator\":\"Kitsu\",\"folder\":\"Booth/Kitsu/Webp\",\"files\":[\"readme.png\",\"Preview.gif\"]}," +
            "{\"store\":\"Booth\",\"name\":\"Plain\",\"creator\":\"Kitsu\",\"folder\":\"Booth/Kitsu/Plain\",\"files\":[\"texture.webp\"]}]}", Encoding.UTF8);
        var cat = HoardCatalog.Load(root, (byte[])null);
        Func<string, string> pic = n => { var x = cat.Assets.Find(y => y.Name == n); return x == null || x.ThumbPath == null ? null : Path.GetFileName(x.ThumbPath); };
        Check("pictures: a GIF thumbnail is shown", pic("Animated") == "_thumbnail.gif", pic("Animated") ?? "none");
        Check("pictures: a WebP thumbnail gives way to a preview among the files", pic("Webp") == "Preview.gif", pic("Webp") ?? "none");
        Check("pictures: none the window can show", pic("Plain") == null, pic("Plain") ?? "none");
        Directory.Delete(root, true);
    }

    static byte[] TopDown(byte[] bottomUp, int w, int h)
    {
        var o = new byte[bottomUp.Length];
        for (int y = 0; y < h; y++) Array.Copy(bottomUp, (h - 1 - y) * w * 4, o, y * w * 4, w * 4);
        return o;
    }

    static string Sha(byte[] b)
    {
        using (var sha = SHA256.Create()) return BitConverter.ToString(sha.ComputeHash(b)).Replace("-", "").ToLowerInvariant();
    }

    // the credits list (issue #51): one entry per product, sorted by creator, left-out ones gone, safe to paste
    static void CreditsChecks()
    {
        var found = new List<CreditEntry> {
            new CreditEntry { Store = "Booth", Name = "Rusk Avatar Base", Creator = "Kitsu Studio", Url = "https://booth.pm/ja/items/1" },
            new CreditEntry { Store = "Gumroad", Name = "Paw Shader", Creator = "abyss", Url = "https://evil.example/x" },
            new CreditEntry { Store = "Jinxxy", Name = "Tail Glow", Creator = "Norspil", Url = "https://jinxxy.com/norspil/tail" },
            new CreditEntry { Store = "Booth", Name = "rusk avatar base", Creator = "Kitsu Studio" },               // the same product again
            new CreditEntry { Store = "Booth", Name = "Hidden ‮gpj.exe\n- fake line", Creator = "Sneaky" },
            new CreditEntry { Store = "Booth", Name = "  ", Creator = "Nobody" },                                   // no name: dropped
            new CreditEntry { Store = "", Name = "Hair Pack", Creator = "", Url = "https://example.com/hair", Added = true },
            new CreditEntry { Store = "", Name = "Old Thing", Creator = "Someone", Url = "http://example.com/", Added = true },
        };
        var left = new HashSet<string>(StringComparer.OrdinalIgnoreCase) { "Jinxxy/Tail Glow" };
        var list = Credits.Build(found, left);
        var names = list.ConvertAll(e => e.Name);
        Check("credits: one per product, left-out ones gone, sorted by creator", string.Join("|", names) ==
              "Paw Shader|Rusk Avatar Base|Hidden gpj.exe - fake line|Old Thing|Hair Pack", string.Join("|", names));
        var hidden = list.Find(e => e.Creator == "Sneaky");
        Check("credits: no control or invisible characters, one line", hidden != null && hidden.Name.IndexOf('\n') < 0 && hidden.Name.IndexOf('‮') < 0);
        Check("credits: a store link that isn't the product's store is dropped", list.Find(e => e.Name == "Paw Shader").Url == null);
        Check("credits: the product's own store link is kept", list.Find(e => e.Name == "Rusk Avatar Base").Url == "https://booth.pm/ja/items/1");
        Check("credits: a link added by hand must be https", list.Find(e => e.Name == "Old Thing").Url == null &&
              list.Find(e => e.Name == "Hair Pack").Url == "https://example.com/hair");
        Check("credits: odd links refused", Credits.Link(null, "javascript:alert(1)", true) == null &&
              Credits.Link(null, "https://a.example/x)(y", true) == null && Credits.Link(null, "https://u:p@a.example/", true) == null);

        var two = Credits.Build(new List<CreditEntry> {
            new CreditEntry { Store = "Booth", Name = "Rusk", Creator = "Kitsu", Url = "https://booth.pm/ja/items/1" },
            new CreditEntry { Store = "Booth", Name = "Ears", Creator = "Kitsu" },
            new CreditEntry { Store = "Itch", Name = "[Pack](javascript:x)", Creator = "Zed_z" } }, null);
        string plain = Credits.Format(two, CreditFormat.List);
        Check("credits: a list", plain == "Assets used\n- Ears by Kitsu (Booth)\n- Rusk by Kitsu (Booth) https://booth.pm/ja/items/1\n" +
              "- [Pack](javascript:x) by Zed_z (itch.io)\n", plain);
        string md = Credits.Format(two, CreditFormat.Markdown, "Credits");
        Check("credits: Markdown, with names that can't become links", md == "## Credits\n\n- Ears by Kitsu (Booth)\n" +
              "- [Rusk](https://booth.pm/ja/items/1) by Kitsu (Booth)\n- \\[Pack\\]\\(javascript:x\\) by Zed\\_z (itch\\.io)\n", md);
        string by = Credits.Format(two, CreditFormat.ByCreator, "");
        Check("credits: by creator", by == "Kitsu: Ears, Rusk\nZed_z: [Pack](javascript:x)\n", by);
        Check("credits: an empty list says so", Credits.Format(new List<CreditEntry>(), CreditFormat.List) == "Assets used\nNone yet.\n");
        Check("credits: cut without splitting a character", Credits.OneLine("ab\U0001F98A", 3) == "ab");

        // what you change is kept per project, and a damaged file starts again rather than failing
        string dir = Path.Combine(Path.GetTempPath(), "hoard-credits-" + Guid.NewGuid().ToString("N"));
        string file = Path.Combine(dir, "Hoard", "credits.json");
        var f = new CreditsFile { Title = "Made with", Format = CreditFormat.Markdown };
        f.Added.Add(new CreditEntry { Store = "", Name = "Hair Pack", Creator = "Mia", Url = "https://example.com/hair", Added = true });
        f.LeftOut.Add("Jinxxy/Tail Glow");
        f.Save(file);
        f.Save(file);   // over an existing one
        var back = CreditsFile.Load(file);
        Check("credits file: kept", back.Title == "Made with" && back.Format == CreditFormat.Markdown && back.LeftOut.Contains("jinxxy/tail glow") &&
              back.Added.Count == 1 && back.Added[0].Name == "Hair Pack" && back.Added[0].Url == "https://example.com/hair" && back.Added[0].Added,
              File.ReadAllText(file));
        File.WriteAllText(file, "{\"format\":\"hoard-unity-credits\",\"style\":\"Evil\",\"title\":\"x\\u0000y\",\"added\":[{\"name\":\"A\",\"url\":\"javascript:x\"},7]}");
        var odd = CreditsFile.Load(file);
        Check("credits file: odd values made safe", odd.Format == CreditFormat.List && odd.Title == "x y" && odd.Added.Count == 1 && odd.Added[0].Url == null);
        File.WriteAllText(file, "{ not json");
        var broken = CreditsFile.Load(file);
        Check("credits file: damaged, starts again", broken.Added.Count == 0 && broken.Title == "Assets used");
        Check("credits file: missing, starts again", CreditsFile.Load(Path.Combine(dir, "none.json")).Format == CreditFormat.List);
        Directory.Delete(dir, true);
    }

    static void Check(string name, bool ok, string detail = "")
    {
        Console.WriteLine((ok ? "PASS " : "FAIL ") + name + (ok ? "" : ": " + detail));
        if (!ok) failures++;
    }

    // Hoard's Projects view (issue #86): the report the window writes, which Hoard's test then reads back, checking
    // it makes the very credits list this code makes.
    static void ProjectChecks(string dir)
    {
        string project = Path.Combine(dir, "My Avatar");
        string file = ProjectReport.FileFor(Path.Combine(dir, "data"), project);
        Check("project report: one file per project", file == ProjectReport.FileFor(Path.Combine(dir, "data"), project + Path.DirectorySeparatorChar)
              && Path.GetFileName(file).Length == 21 && Path.GetDirectoryName(file) == Path.Combine(dir, "data", "projects"), file);
        var assets = new List<ProjectAsset>
        {
            new ProjectAsset { Store = "Booth", Name = "Rusk Avatar Base", Creator = "Kitsu Studio", Folder = "Booth/Kitsu Studio/Rusk Avatar Base",
                               Url = "https://booth.pm/ja/items/1", Status = "yes" },
            new ProjectAsset { Store = "Itch", Name = "Paw Suit", Creator = "Kitsu Studio", Folder = "Itch/Kitsu Studio/Paw Suit",
                               Url = "https://kitsu.itch.io/paw-suit", Status = "yes" },
            new ProjectAsset { Store = "Gumroad", Name = "Tail Glow", Creator = "Mochi Works", Folder = "Gumroad/Mochi Works/Tail Glow", Status = "yes" },
            new ProjectAsset { Store = "Jinxxy", Name = "Half There", Creator = "Anko", Folder = "Jinxxy/Anko/Half There", Status = "partly" },
            new ProjectAsset { Store = "Booth", Name = "Gone Now", Creator = "Anko", Folder = "Booth/Anko/Gone Now", Status = "imported" },
        };
        var credits = new CreditsFile { Title = "Made with [love]", Format = CreditFormat.Markdown };
        credits.Added.Add(new CreditEntry { Store = "", Name = "Hair_Pack", Creator = "Mia", Url = "https://example.com/hair", Added = true });
        credits.LeftOut.Add("Gumroad/Tail Glow");
        var report = ProjectReport.Build(project, "My Avatar", "2022.3.22f1", "2026-10-01T12:00:00+00:00", assets, credits);
        Check("project report: written", ProjectReport.Write(file, report));
        Check("project report: not written again when nothing changed", !ProjectReport.Write(file, report));
        // the list the window would make: what's all in the project, and what you added, less what you left out
        var found = new List<CreditEntry>();
        foreach (var a in assets) if (a.Status == "yes") found.Add(new CreditEntry { Store = a.Store, Name = a.Name, Creator = a.Creator, Url = a.Url });
        found.AddRange(credits.Added);
        var list = Credits.Build(found, credits.LeftOut);
        foreach (CreditFormat style in Enum.GetValues(typeof(CreditFormat)))
            File.WriteAllText(Path.Combine(dir, "project_credits_" + style + ".txt"), Credits.Format(list, style, credits.Title), new UTF8Encoding(false));
        File.WriteAllText(Path.Combine(dir, "project_report_path.txt"), file);
    }

    public static int Main(string[] args)
    {
        string dir = args[0];
        byte[] key = Seal.ReadKey(Path.Combine(dir, "integrity.key"));
        Check("key read", key != null && key.Length == 32);
        Check("key id matches Hoard's", Seal.KeyId(key) == File.ReadAllText(Path.Combine(dir, "key_id.txt")).Trim());

        // canonical JSON: byte for byte what Python's json.dumps(sort_keys, (",", ":"), ensure_ascii=False) makes
        var cases = Json.Parse(File.ReadAllText(Path.Combine(dir, "canonical_cases.json"), Encoding.UTF8));
        var expected = File.ReadAllLines(Path.Combine(dir, "canonical_sha256.txt"));
        for (int n = 0; n < cases.Items.Count; n++)
        {
            string got;
            using (var sha = SHA256.Create()) got = BitConverter.ToString(sha.ComputeHash(Json.Canonical(cases.Items[n]))).Replace("-", "").ToLowerInvariant();
            Check("canonical case " + n, got == expected[n], Encoding.UTF8.GetString(Json.Canonical(cases.Items[n])));
        }

        // seals
        var states = new Dictionary<string, SealState> {
            { "sealed", SealState.Sealed }, { "edited", SealState.Changed }, { "unsealed", SealState.Unsealed } };
        foreach (var kv in states)
        {
            var doc = Json.Parse(File.ReadAllText(Path.Combine(dir, "seal_" + kv.Key + ".json"), Encoding.UTF8));
            Check("seal " + kv.Key, Seal.Check(doc, key) == kv.Value, Seal.Check(doc, key).ToString());
        }
        var sealedDoc = Json.Parse(File.ReadAllText(Path.Combine(dir, "seal_sealed.json"), Encoding.UTF8));
        var otherKey = new byte[32];
        Check("seal from another computer", Seal.Check(sealedDoc, otherKey) == SealState.Foreign);
        Check("seal without the key", Seal.Check(sealedDoc, (byte[])null) == SealState.NoKey);

        // the catalog: every documented promise re-checked, links dropped when the seal doesn't match
        var cat = HoardCatalog.Load(Path.Combine(dir, "root"), key);
        Check("catalog loads", cat.Problem == null, cat.Problem ?? "");
        Check("catalog is sealed", cat.SealStatus == SealState.Sealed, cat.SealStatus.ToString());
        var names = new List<string>();
        foreach (var a in cat.Assets) names.Add(a.Name);
        Check("only the good entries", string.Join("|", names) == File.ReadAllText(Path.Combine(dir, "good_names.txt")).Trim(), string.Join("|", names));
        Check("broken entries counted", cat.LeftOut == int.Parse(File.ReadAllText(Path.Combine(dir, "left_out.txt")).Trim()), cat.LeftOut.ToString());
        var good = cat.Assets.Find(a => a.Name == "Rusk Avatar Base");
        Check("store link kept", good != null && good.Url == "https://booth.pm/ja/items/1", good == null ? "missing" : good.Url ?? "null");
        var itch = cat.Assets.Find(a => a.Name == "Paw Suit");
        Check("an itch.io asset, with its link", itch != null && itch.Store == "Itch" && itch.Url == "https://kitsu.itch.io/paw-suit"
              && cat.FilePath(itch, "PawSuit.unitypackage") != null, itch == null ? "missing" : itch.Url ?? "null");
        var badLink = cat.Assets.Find(a => a.Name == "Odd Link");
        Check("off-store link dropped", badLink != null && badLink.Url == null);
        Check("file found inside the folder", good != null && cat.FilePath(good, "Rusk.unitypackage") != null);
        Check("thumbnail found", good != null && cat.Thumbnail(good) != null);
        var linked = cat.Assets.Find(a => a.Name == "Linked Away");
        Check("never through a planted link", linked != null && cat.FilePath(linked, "secret.txt") == null && cat.FolderPath(linked) == null);
        Check("missing file is null", good != null && cat.FilePath(good, "nope.zip") == null);
        var mine = cat.Assets.Find(a => a.Name == "My Textures");
        Check("a Local item listed where it is", mine != null && mine.Store == "Local" && mine.Note == "A commission"
              && cat.FilePath(mine, "Mine.unitypackage") != null && cat.FolderPath(mine) == Path.GetFullPath(Path.Combine(dir, "mine"))
              && mine.PackagePaths.Count == 1 && mine.ThumbPath != null, mine == null ? "missing" : mine.Location ?? "no place");

        var edited = HoardCatalog.Load(Path.Combine(dir, "root_edited"), key);
        Check("edited catalog: seal says so", edited.SealStatus == SealState.Changed, edited.SealStatus.ToString());
        Check("edited catalog: no links trusted", edited.Assets.TrueForAll(a => a.Url == null));
        Check("edited catalog: no Local folder outside trusted", !edited.Assets.Exists(a => a.Location != null));

        // path, link and text rules
        foreach (string p in new[] { "../x", "/abs", "a//b", "a/./b", "C:/x", "a\\b", "a:b", "a/b?", "a\u202eb" })
            Check("path refused: " + p, !HoardCatalog.PlainPath(p));
        Check("plain path ok", HoardCatalog.PlainPath("Booth/Kitsu Studio/Rusk ラスク"));
        foreach (string u in new[] { "http://booth.pm/x", "https://booth.pm.evil.example/x", "https://user@booth.pm/x", "https://booth.pm:8443/x", "javascript:alert(1)" })
            Check("link refused: " + u, !HoardCatalog.StoreLink("Booth", u));
        Check("shop subdomain ok", HoardCatalog.StoreLink("Booth", "https://kitsu.booth.pm/items/1"));
        Check("itch.io creator page ok", HoardCatalog.StoreLink("Itch", "https://kitsu.itch.io/paw-suit"));
        foreach (string u in new[] { "https://itch.io.evil.example/x", "https://evil-itch.io/x", "https://kitsu.booth.pm/items/1" })
            Check("itch.io link refused: " + u, !HoardCatalog.StoreLink("Itch", u));
        Check("itch.io named as people write it", HoardCatalog.StoreLabel("Itch") == "itch.io" && HoardCatalog.StoreLabel("Booth") == "Booth");

        // a Unity package: every GUID and path, nothing extracted
        var assets = UnityPackageReader.ReadAssets(Path.Combine(dir, "test.unitypackage"));
        var want = File.ReadAllLines(Path.Combine(dir, "package_expected.txt"));
        var gotLines = new List<string>();
        foreach (var kv in assets) gotLines.Add(kv.Key + " " + kv.Value);
        gotLines.Sort(StringComparer.Ordinal);
        Check("package GUIDs and paths", string.Join("\n", gotLines) == string.Join("\n", want), string.Join(" / ", gotLines));
        try { UnityPackageReader.ReadAssets(Path.Combine(dir, "not_a_package.unitypackage")); Check("not a package refused", false, "no error"); }
        catch (Exception e) { Check("not a package refused", e is InvalidDataException || e is IOException, e.GetType().Name); }
        // hostile packages: what a header claims is checked before it's acted on (an 8 GiB name would be allocated)
        try { UnityPackageReader.ReadAssets(Path.Combine(dir, "huge_name.unitypackage")); Check("a huge long name refused", false, "no error"); }
        catch (Exception e) { Check("a huge long name refused before anything is allocated", e is InvalidDataException, e.GetType().Name); }
        try { UnityPackageReader.ReadAssets(Path.Combine(dir, "too_big.unitypackage")); Check("a package larger than any real one refused", false, "no error"); }
        catch (Exception e)
        {
            Check("a package larger than any real one refused", e is InvalidDataException && e.Message.Contains("larger"),
                  e.GetType().Name + ": " + e.Message);
        }

        // the release's own .unitypackage (built by scripts/build_vpm.py), read back by this reader
        string release = Path.Combine(dir, "release.unitypackage");
        if (File.Exists(release))
        {
            var got = new List<string>();
            foreach (var kv in UnityPackageReader.ReadAssets(release)) got.Add(kv.Key + " " + kv.Value);
            got.Sort(StringComparer.Ordinal);
            var expect = new List<string>(File.ReadAllLines(Path.Combine(dir, "release_expected.txt"), Encoding.UTF8));
            Check("the release .unitypackage reads back", string.Join("\n", got) == string.Join("\n", expect),
                  got.Count + " entries, expected " + expect.Count);
        }

        // several keys: the seal is checked with whichever of this account's keys it names
        byte[] keyB = Seal.ReadKey(Path.Combine(dir, "other.key"));
        var byB = Json.Parse(File.ReadAllText(Path.Combine(dir, "seal_other_key.json"), Encoding.UTF8));
        Check("sealed by a second key: found among the keys", Seal.Check(byB, new List<byte[]> { key, keyB }) == SealState.Sealed);
        Check("sealed by a key this account doesn't have", Seal.Check(byB, new List<byte[]> { key }) == SealState.Foreign);
        Check("no keys at all", Seal.Check(byB, new List<byte[]>()) == SealState.NoKey);
        var tampered = Json.Parse(File.ReadAllText(Path.Combine(dir, "seal_other_key_edited.json"), Encoding.UTF8));
        Check("an edit is still caught with the right key among others", Seal.Check(tampered, new List<byte[]> { key, keyB }) == SealState.Changed);
        var both = Seal.ReadKeys(new[] { Path.Combine(dir, "integrity.key"), Path.Combine(dir, "other.key"), Path.Combine(dir, "integrity.key"), Path.Combine(dir, "missing.key") });
        Check("keys read once each, missing ones skipped", both.Count == 2);

        // where this account's keys can be: Hoard's folder, and Microsoft Store Python's private copy (Windows)
        string local = Path.Combine(dir, "localappdata");
        var onWindows = HoardLocation.KeyFiles(Path.Combine(local, "Hoard"), local, true);
        Check("Store Python's copy found on Windows", onWindows.Count == 2 && onWindows[1].Contains("PythonSoftwareFoundation.Python.3.12_qbz5n2kfra8p0"), string.Join(";", onWindows));
        Check("only Hoard's folder elsewhere", HoardLocation.KeyFiles(Path.Combine(local, "Hoard"), local, false).Count == 1);

        // what the window needs is worked out while loading, not while drawing
        Check("files resolved when loading", good != null && good.PackagePaths.Count == 1 && good.PackagePaths[0].EndsWith("Rusk.unitypackage"));
        Check("picture resolved when loading", good != null && good.ThumbPath != null && good.ThumbPath.EndsWith("_thumbnail.png"));
        Check("search text ready", good != null && good.SearchText.Contains("kitsu studio") && good.HasPackages);
        Check("a planted link resolves to nothing", linked != null && linked.PackagePaths.Count == 0 && linked.ThumbPath == null);

        // only the rows on screen are drawn
        int first, last;
        ListView.VisibleRange(0, 520, 52, 3000, out first, out last);
        Check("top of a long list", first == 0 && last == 10, first + ".." + last);
        ListView.VisibleRange(52 * 1000, 520, 52, 3000, out first, out last);
        Check("middle of a long list", first == 999 && last == 1010, first + ".." + last);
        ListView.VisibleRange(52 * 2995, 520, 52, 3000, out first, out last);
        Check("end of a long list", last == 2999, first + ".." + last);
        ListView.VisibleRange(0, 520, 52, 0, out first, out last);
        Check("an empty list draws nothing", last < first);

        // a big library: loaded quickly, with each shared folder checked once
        var watch = System.Diagnostics.Stopwatch.StartNew();
        var big = HoardCatalog.Load(Path.Combine(dir, "root_big"), key);
        watch.Stop();
        int wanted = int.Parse(File.ReadAllText(Path.Combine(dir, "big_count.txt")).Trim());
        Check("big library: every product loaded", big.Problem == null && big.Assets.Count == wanted, big.Problem ?? big.Assets.Count.ToString());
        Check("big library: every file and picture resolved", big.Assets.TrueForAll(a => a.PackagePaths.Count == 1 && a.ThumbPath != null));
        Check("big library: shared folders checked once", big.DiskChecks <= wanted * 3 + 200, big.DiskChecks + " disk checks for " + wanted + " products");
        Console.WriteLine("INFO big library: " + wanted + " products in " + watch.ElapsedMilliseconds + " ms, " + big.DiskChecks + " disk checks");
        Check("big library: loaded in under 10 seconds", watch.ElapsedMilliseconds < 10000, watch.ElapsedMilliseconds + " ms");

        CreditsChecks();
        GifChecks(Path.Combine(dir, "gifs"));
        PictureChecks(Path.Combine(dir, "gifs"));
        ProjectChecks(dir);

        Console.WriteLine(failures == 0 ? "ALL PASSED" : failures + " FAILED");
        return failures == 0 ? 0 : 1;
    }
}
