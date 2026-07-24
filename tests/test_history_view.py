import pytest
from types import SimpleNamespace as SN
from datetime import datetime, timezone

class FakeMember:
    def __init__(self, id=1, name="TestUser"):
        self.id = id
        self.name = name
        self.display_name = name
        self.mention = f"<@{id}>"
        self.display_avatar = SN(url="https://example.com/avatar.png")
        self.guild_permissions = SN(view_audit_log=True, manage_messages=True, kick_members=True, ban_members=True)


class FakeGuild:
    def __init__(self, id=10, name="TestGuild"):
        self.id = id
        self.name = name

    def get_member(self, member_id):
        return FakeMember(id=member_id)

class FakeCtx:
    def __init__(self, author=None, guild=None):
        self.author = author or FakeMember(id=1, name="ModUser")
        self.guild = guild or FakeGuild()
        self.sent = []

    async def send(self, content=None, embed=None, view=None, **kwargs):
        if content:
            self.sent.append(content)
        if embed:
            self.sent.append(embed)
        if view:
            self.sent.append(view)

@pytest.mark.asyncio
async def test_paginated_history_view(monkeypatch):
    import cogs.moderation as mod_cog

    bot = SN()
    cog = mod_cog.Moderation(bot=bot)

    guild = FakeGuild()
    target = FakeMember(id=2, name="TargetUser")
    now_iso = datetime.now(timezone.utc).isoformat()

    sample_logs = [
        {"case_id": 1, "action": "vcmute", "moderator_id": 1, "created_at": now_iso, "reason": "abuse 10hr"},
        {"case_id": 2, "action": "vcmute", "moderator_id": 1, "created_at": now_iso, "reason": "Second VC mute"},
        {"case_id": 3, "action": "vcunmute", "moderator_id": 1, "created_at": now_iso, "reason": "Auto unmute"},
    ]

    async def fake_fetch(guild_id, target_id):
        return sample_logs

    import utils.modlog as modlog_module
    monkeypatch.setattr(mod_cog, "fetch_logs_for_target", fake_fetch)
    monkeypatch.setattr(modlog_module, "fetch_logs_for_target", fake_fetch)

    ctx = FakeCtx(guild=guild)
    await cog.history.callback(cog, ctx, target=target)

    # 1. Verify default view is Vc_Mute
    views = [s for s in ctx.sent if type(s).__name__ == "HistorySelectView"]
    assert views, f"Expected HistorySelectView in ctx.sent, but got: {ctx.sent}"
    view = views[0]

    assert view.current_category == "vcmute"
    embed_vcmute = view.build_embed()
    assert "Vc_Mute History for TargetUser" in embed_vcmute.title
    assert "Case #1" in embed_vcmute.fields[0].name
    assert "Page 1/2" in embed_vcmute.footer.text

    # 2. Test pagination to next record
    assert not view.btn_next.disabled
    view.current_page = 1
    view.update_buttons()
    embed_page2 = view.build_embed()
    assert "Case #2" in embed_page2.fields[0].name
    assert "Page 2/2" in embed_page2.footer.text
    assert view.btn_next.disabled

    # 3. Test category switch to Unmute via dropdown
    view.current_category = "unmute"
    view.current_page = 0
    view.update_buttons()
    embed_unmute = view.build_embed()
    assert "Unmute History for TargetUser" in embed_unmute.title
    assert "Case #3" in embed_unmute.fields[0].name
    assert "Page 1/1" in embed_unmute.footer.text
