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

    static void Check(string name, bool ok, string detail = "")
    {
        Console.WriteLine((ok ? "PASS " : "FAIL ") + name + (ok ? "" : ": " + detail));
        if (!ok) failures++;
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

        var edited = HoardCatalog.Load(Path.Combine(dir, "root_edited"), key);
        Check("edited catalog: seal says so", edited.SealStatus == SealState.Changed, edited.SealStatus.ToString());
        Check("edited catalog: no links trusted", edited.Assets.TrueForAll(a => a.Url == null));

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

        Console.WriteLine(failures == 0 ? "ALL PASSED" : failures + " FAILED");
        return failures == 0 ? 0 : 1;
    }
}
