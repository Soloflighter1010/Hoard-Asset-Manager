"""Per-project policy, download coordination and opt-in revalidation."""
import io
import threading
from types import SimpleNamespace as NS
from unittest import mock
from tests.test_vpm_projects import Temp, make_unitypackage, SAMPLE, G2
from hoard.vpm import autoupdate, listing, managed, unitypackage
from hoard.vpm.project import UnityProject
from hoard.vpm.api import ProjectsError


class Updates(Temp):
    def jobs(self):
        calls = []
        jobs = NS(state={"running":False,"queue":[],"job_id":None},history=[],calls=calls)
        def start(task, stores, **kwargs):
            calls.append((task, stores, kwargs))
            jobs.state["job_id"] = "job" + str(len(calls))
            return "started"
        jobs.start = start
        jobs.tasks = lambda: {"history":jobs.history}
        return jobs

    def server(self, path):
        return NS(cfg={"setup_done":True},_background_stop=threading.Event(),jobs=self.jobs(),project_jobs=self.jobs(),
                  vpm=NS(listed=lambda p:p))

    def test_modes_persist_and_off_is_the_default(self):
        path = str(self.project())
        self.assertEqual(autoupdate.preference(path), "off")
        for mode in autoupdate.MODES:
            autoupdate.configure(path, mode)
            self.assertEqual(autoupdate.preference(path), mode)
        with self.assertRaises(ValueError):
            autoupdate.configure(path, "invalid")

    def test_tick_defers_open_unity_busy_lanes_and_respects_interval(self):
        path = str(self.project())
        server = self.server(path)
        autoupdate.configure(path, "packages")
        with mock.patch.object(UnityProject,"unity_running",return_value=True):
            self.assertFalse(autoupdate.tick(server,10000))
        with mock.patch.object(UnityProject,"unity_running",return_value=False):
            server.jobs.state["running"] = True
            self.assertFalse(autoupdate.tick(server,10000))
            server.jobs.state["running"] = False
            self.assertTrue(autoupdate.tick(server,10000))
            self.assertEqual(server.project_jobs.calls[0][2]["project"]["op"],"auto-update")
            self.assertFalse(autoupdate.tick(server,10060))

    def test_assets_check_then_download_then_apply(self):
        path = str(self.project())
        server = self.server(path)
        autoupdate.configure(path,"assets")
        listing.add_preloaded(path,[{"tag_key":"booth:product","file":"asset.unitypackage","kind":"unitypackage"}])
        with mock.patch.object(UnityProject,"unity_running",return_value=False), mock.patch("hoard.asset_updates.AssetUpdates.load",return_value={"items":{"booth:product":{}}}):
            self.assertTrue(autoupdate.tick(server,10000))
            self.assertEqual(server.jobs.calls[-1][0],"check-updates")
            server.jobs.history.append({"id":"job1","outcome":"done"})
            self.assertTrue(autoupdate.tick(server,10060))
            self.assertEqual(server.jobs.calls[-1][0],"download")
            server.jobs.history.append({"id":"job2","outcome":"done"})
            self.assertTrue(autoupdate.tick(server,10120))
            self.assertIsNone(server.project_jobs.calls[-1][2]["project"]["download_error"])

    def test_failed_download_blocks_apply_and_disabling_cancels_queued_work(self):
        path = str(self.project())
        server = self.server(path)
        autoupdate.configure(path,"both")
        listing.note(path,auto_pending={"phase":"download","job":"failed"})
        server.jobs.history.append({"id":"failed","outcome":"failed"})
        with mock.patch.object(UnityProject,"unity_running",return_value=False):
            self.assertTrue(autoupdate.tick(server,10000))
        self.assertIn("did not finish",server.project_jobs.calls[-1][2]["project"]["download_error"])
        autoupdate.configure(path,"off")
        self.assertIn("off",autoupdate.run(None,path,lambda key:None))

    def test_asset_mode_updates_tracked_files_without_using_repositories(self):
        path = self.project()
        imported = unitypackage.place(path,io.BytesIO(make_unitypackage(SAMPLE)))
        managed.record(path,imported.baselines,"booth:product")
        autoupdate.configure(str(path),"assets")
        folder = self.tmp / "downloads"
        folder.mkdir()
        (folder / "new.unitypackage").write_bytes(make_unitypackage({G2:(SAMPLE[G2][0],b"new asset")}))
        listing.add_preloaded(str(path),[{"tag_key":"booth:product","file":"new.unitypackage","kind":"unitypackage"}])
        asset = {"tag_key":"booth:product","abs_folder":str(folder),"files":[{"path":"new.unitypackage"}]}
        with mock.patch.object(UnityProject,"unity_running",return_value=False):
            result = autoupdate.run(None,str(path),lambda key:asset)
        self.assertIn("1 managed assets updated",result)
        self.assertEqual((path / SAMPLE[G2][0]).read_bytes(),b"new asset")

    def test_package_mode_rejects_conflicts(self):
        path = str(self.project())
        autoupdate.configure(path,"packages")
        service = NS(collection=lambda:NS(refresh=lambda:[]),forget=lambda:None,_fetch_missing=lambda:None,
                     changes=lambda p,r:NS(conflicts={"tool":NS(packages=["conflict"],unity=False,unlocked=[])}))
        with mock.patch.object(UnityProject,"unity_running",return_value=False), self.assertRaisesRegex(ProjectsError,"conflicts"):
            autoupdate.run(service,path,lambda key:None)

    def test_package_mode_uses_verified_apply_and_never_touches_assets(self):
        path = str(self.project())
        autoupdate.configure(path,"packages")
        apply = mock.Mock(return_value=["tool 1.0 -> 2.0"])
        asset_lookup = mock.Mock(side_effect=AssertionError("packages mode must not import assets"))
        service = NS(collection=lambda:NS(refresh=lambda:[]),forget=lambda:None,_fetch_missing=lambda:None,
                     changes=lambda p,r:NS(conflicts={},empty=lambda:False),_apply=apply)
        with mock.patch.object(UnityProject,"unity_running",return_value=False):
            self.assertIn("1 package changes",autoupdate.run(service,path,asset_lookup))
        apply.assert_called_once()
        asset_lookup.assert_not_called()

    def test_both_mode_runs_packages_and_assets(self):
        path = str(self.project())
        autoupdate.configure(path,"both")
        listing.add_preloaded(path,[{"tag_key":"booth:product","file":"asset.unitypackage","kind":"unitypackage"}])
        apply = mock.Mock(return_value=["tool 1.0 -> 2.0"])
        service = NS(collection=lambda:NS(refresh=lambda:[]),forget=lambda:None,_fetch_missing=lambda:None,
                     changes=lambda p,r:NS(conflicts={},empty=lambda:False),_apply=apply)
        asset={"tag_key":"booth:product","abs_folder":str(self.tmp),"files":[{"path":"asset.unitypackage"}]}
        with mock.patch.object(UnityProject,"unity_running",return_value=False), mock.patch.object(managed,"update_file",return_value={"updated":2,"skipped":0}) as update:
            self.assertIn("2 managed assets updated",autoupdate.run(service,path,lambda key:asset))
        apply.assert_called_once()
        update.assert_called_once()
