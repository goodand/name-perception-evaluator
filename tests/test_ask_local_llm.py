"""로컬 LLM(LM Studio) 답변자 입력 형식 명세.

2026-11-05 실측: 이름을 'C01 random-name-generator' 한 줄로 보내자 qwen3.8-27b가 id 칸에 'C01 random-name-generator'를
써서 id/term 불일치로 실패했다. id와 이름을 JSON으로 나눠 보낸다(claude·gpt 실행기와 같은 방식).
"""
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
import ask_local_llm as al  # noqa: E402


def test_names_sent_as_json(monkeypatch):
    sent = {}

    def fake_urlopen(req, timeout):
        sent["body"] = json.loads(req.data.decode("utf-8"))
        reply = '{"items":[{"id":"C01","term":"a-b","explanation":"x"}]}'
        return io.StringIO(json.dumps({"choices": [{"message": {"content": reply}}]}))

    monkeypatch.setattr(al.urllib.request, "urlopen", fake_urlopen)
    out = al.ask("m", [{"id": "C01", "term": "a-b"}], prompt="P\n\n")
    content = sent["body"]["messages"][0]["content"]
    payload = json.loads(content[content.index("["):])
    assert payload == [{"id": "C01", "term": "a-b"}]
    assert out == [{"id": "C01", "term": "a-b", "explanation": "x"}]
