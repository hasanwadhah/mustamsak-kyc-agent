import json
from contextlib import nullcontext
from unittest.mock import Mock
import pytest
from app import launcher


def isolate(monkeypatch, tmp_path):
    monkeypatch.setattr(launcher, 'ROOT', tmp_path)
    monkeypatch.setattr(launcher, 'launch_lock', lambda *a: nullcontext())
    monkeypatch.setattr(launcher, 'revision', lambda: 'new')


def test_ready_server_is_reused_without_starting_another(monkeypatch, tmp_path):
    isolate(monkeypatch,tmp_path)
    monkeypatch.setattr(launcher,'health',lambda url: {'instance':launcher.INSTANCE,'revision':'new','pid':123})
    spawn=Mock();monkeypatch.setattr(launcher.subprocess,'Popen',spawn)
    assert launcher.ensure_server()==('http://127.0.0.1:8765','reused')
    spawn.assert_not_called()


@pytest.mark.parametrize('running',[
    {'instance':'another-installation','revision':'old','pid':123},
    {'instance':launcher.INSTANCE,'revision':'old','pid':123,'busy':True},
    {'instance':launcher.INSTANCE,'revision':'old','pid':123,'busy':False},
])
def test_foreign_busy_or_unrecorded_server_is_never_killed(monkeypatch,tmp_path,running):
    isolate(monkeypatch,tmp_path)
    monkeypatch.setattr(launcher,'health',lambda url: running)
    kill=Mock();monkeypatch.setattr(launcher.subprocess,'run',kill)
    with pytest.raises(RuntimeError):launcher.ensure_server()
    kill.assert_not_called()


def test_browser_is_not_opened_after_startup_failure(monkeypatch):
    monkeypatch.setattr(launcher.sys,'argv',['launcher'])
    monkeypatch.setattr(launcher,'ensure_server',Mock(side_effect=RuntimeError('startup failed')))
    browser=Mock();monkeypatch.setattr(launcher.webbrowser,'open',browser)
    assert launcher.main()==1
    browser.assert_not_called()


def test_startup_waits_for_health_and_records_the_actual_server_pid(monkeypatch,tmp_path):
    isolate(monkeypatch,tmp_path)
    monkeypatch.setattr(launcher,'health',Mock(side_effect=[None,None,{'instance':launcher.INSTANCE,'revision':'new','pid':321}]))
    monkeypatch.setattr(launcher,'occupied',lambda port:False)
    monkeypatch.setattr(launcher.time,'sleep',lambda seconds:None)
    process=Mock();process.poll.return_value=None
    monkeypatch.setattr(launcher.subprocess,'Popen',Mock(return_value=process))
    assert launcher.ensure_server()[1]=='started'
    saved=json.loads((tmp_path/'output/runtime/server-8765.json').read_text())
    assert saved['pid']==321

