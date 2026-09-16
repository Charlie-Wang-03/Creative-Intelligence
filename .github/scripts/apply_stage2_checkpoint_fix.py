from pathlib import Path


path = Path("mathematical-concept-agent/agent.py")
text = path.read_text(encoding="utf-8")
old = '''def _checkpoint_fields(checkpoint):
    """Mirror one committed checkpoint onto the public state fields."""
    return {
        "turn": int(checkpoint["turn"]),
        "summary": checkpoint.get("summary", ""),
        "next_step": checkpoint.get("next_step", ""),
        "skills_used": list(checkpoint.get("skills_used", [])),
        "checkpoint": checkpoint,
    }
'''
new = '''def _checkpoint_fields(checkpoint):
    """Mirror one committed checkpoint onto the public state fields."""
    return {
        "turn": int(checkpoint["turn"]),
        "summary": checkpoint.get("summary", ""),
        "next_step": checkpoint.get("next_step", ""),
        "skills_used": list(checkpoint.get("skills_used", [])),
    }
'''
if text.count(old) != 1:
    raise RuntimeError("expected exactly one checkpoint mirror block")
path.write_text(text.replace(old, new), encoding="utf-8", newline="\n")
