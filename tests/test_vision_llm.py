"""Local contextual reader (Ollama): a vote for doubtful fields, never the sole authority."""
import numpy as np
import pytest

from app import understanding as u, vision_llm


@pytest.fixture
def local_model(monkeypatch):
    answers = {}
    monkeypatch.setattr(vision_llm, 'available', lambda: True)

    def ask(prompt, rgb, schema, timeout=120):
        assert rgb.size > 0 and 'Never guess' in prompt or 'Do not add' in prompt
        return answers.get('number' if 'digits' in schema['properties'] else 'text', {'readable': False})
    monkeypatch.setattr(vision_llm, '_ask', ask)
    return answers


def card():
    return np.full((400, 700, 3), 230, np.uint8)


def number(value, **extra):
    return u.field('house_number', value, .8, [[100, 200], [200, 200], [200, 260], [100, 260]], 'eastern_digit_model',
                   'approximate', **extra)


def test_the_local_model_only_ever_adds_a_suggestion(local_model):
    local_model['number'] = {'digits': '١٥', 'readable': True}
    fields = {'house_number': number('45', single_reader=True)}
    vision_llm.review_housing(card(), fields)
    f = fields['house_number']
    assert f['value'] == '45' and f['status'] == 'approximate'  # never changed by this reader
    assert f['candidates'][-1]['value'] == '15' and f['candidates'][-1]['engine'] == 'local_vision_llm'


def test_off_by_default(monkeypatch):
    monkeypatch.delenv('MUSTAMSAK_LOCAL_VLM', raising=False)
    assert not vision_llm.enabled()


def test_unreadable_answers_change_nothing_and_confirmed_fields_are_not_asked(local_model):
    fields = {'house_number': number('45', single_reader=True)}
    vision_llm.review_housing(card(), fields)  # model said readable=false
    assert fields['house_number']['value'] == '45' and fields['house_number']['status'] == 'approximate'
    local_model['number'] = {'digits': '99', 'readable': True}
    manual = {'house_number': u.field('house_number', '12', None, [[1, 1], [9, 1], [9, 9], [1, 9]], 'manual', 'manual')}
    agreed = {'house_number': number('15', agreement=True)}
    vision_llm.review_housing(card(), manual)
    vision_llm.review_housing(card(), agreed)
    assert manual['house_number']['value'] == '12' and agreed['house_number']['value'] == '15'


def test_names_only_get_a_suggestion(local_model):
    local_model['text'] = {'text': 'كريم سعيد جواد', 'readable': True}
    name = u.field('name', 'كريع سعيلا جو', .7, [[100, 100], [400, 100], [400, 150], [100, 150]], 'housing_label_line', 'approximate')
    fields = {'name': name}
    vision_llm.review_housing(card(), fields)
    assert fields['name']['value'] == 'كريع سعيلا جو'
    assert fields['name']['candidates'][0] == {'value': 'كريم سعيد جواد', 'confidence': None, 'engine': 'local_vision_llm',
                                               'note': 'قراءة القارئ الذكي المحلي؛ اقتراح يحتاج مقارنة بالصورة.'}


def test_without_ollama_nothing_happens(monkeypatch):
    monkeypatch.setattr(vision_llm, 'available', lambda: False)
    fields = {'house_number': number('45', single_reader=True)}
    assert vision_llm.review_housing(card(), fields)['house_number']['value'] == '45'


def test_switch_is_saved_and_applies_immediately(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from app import main, storage
    monkeypatch.setattr(storage, 'DATA', tmp_path)
    for folder in ('batches', 'images', 'exports'):
        (tmp_path / folder).mkdir(exist_ok=True)
    started = []
    monkeypatch.setattr(vision_llm, 'ensure_ollama', lambda wait=15: started.append(True) or False)
    monkeypatch.setattr(vision_llm, '_ollama_version', lambda: None)
    with TestClient(main.app) as client:
        assert client.get('/api/local-ai').json()['enabled'] is False
        state = client.put('/api/local-ai', json={'enabled': True}).json()
        assert state['enabled'] is True and state['ready'] is False and started  # tried to start Ollama
        assert vision_llm.enabled() and '"local_vlm": true' in vision_llm.settings_file().read_text(encoding='utf-8')
        assert client.put('/api/local-ai', json={'enabled': False}).json()['enabled'] is False
        assert not vision_llm.available()
        assert client.put('/api/local-ai', json={'enabled': 'maybe'}).status_code == 422


def test_saved_choice_wins_over_the_environment(monkeypatch):
    monkeypatch.setenv('MUSTAMSAK_LOCAL_VLM', '1')
    assert vision_llm.enabled()
    vision_llm.settings_file().write_text('{"local_vlm": false}', encoding='utf-8')
    assert not vision_llm.enabled()
