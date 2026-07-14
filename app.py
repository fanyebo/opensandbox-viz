"""OpenSandbox Dashboard"""
import streamlit as st, httpx, os, time, base64, json

st.set_page_config(page_title="OpenSandbox Viz", page_icon="📦", layout="wide")

CONFIG_FILE = os.path.join(os.path.expanduser("~"), ".opensandbox-viz.json")

def _load_config():
    try:
        with open(CONFIG_FILE) as f: return json.load(f)
    except: return {}

def _save_config():
    with open(CONFIG_FILE, "w") as f:
        json.dump({"osb_base": _base(), "osb_key": _key(), "osb_proxy": st.session_state.osb_proxy}, f)

cfg = _load_config()
KEY = os.getenv("OSB_API_KEY", cfg.get("osb_key", "dev-api-key-change-in-production"))
BASE = os.getenv("OSB_API_BASE", cfg.get("osb_base", "http://localhost:8080/v1"))

if "osb_key" not in st.session_state: st.session_state.osb_key = KEY
if "osb_base" not in st.session_state: st.session_state.osb_base = BASE
if "osb_proxy" not in st.session_state: st.session_state.osb_proxy = cfg.get("osb_proxy", False)
if "subpage" not in st.session_state: st.session_state.subpage = None
# ponytail: pagination state
if "sb_page" not in st.session_state: st.session_state.sb_page = 1
if "sb_size" not in st.session_state: st.session_state.sb_size = 20

def _key(): return st.session_state.osb_key
def _base(): return st.session_state.osb_base.rstrip("/")

_client = httpx.Client(transport=httpx.HTTPTransport(retries=1), http1=True, http2=False, timeout=30)

def api(path, method="GET", **kw):
    h = {"OPEN-SANDBOX-API-KEY": _key()}
    try: return _client.request(method, f"{_base()}{path}", headers=h, **kw)
    except Exception as e: st.error(f"API: {e}"); return httpx.Response(500)

def execd(sid, port, method, path, **kw):
    r = api(f"/sandboxes/{sid}/endpoints/{port}")
    if r.status_code != 200: st.error(f"endpoint fail: {r.text}"); return httpx.Response(500)
    ep = r.json()
    h = ep.get("headers", {})
    base = ep.get("endpoint") or ep.get("url", "")
    if not base.startswith("http"): base = f"http://{base}"
    return _client.request(method, f"{base.rstrip('/')}{path}", headers=h, **kw)

def fetch(page=1, size=20):
    """Return (items, pagination_dict)."""
    r = api(f"/sandboxes?page={page}&pageSize={size}")
    if r.status_code != 200: return [], {}
    d = r.json()
    items = d if isinstance(d, list) else d.get("items", [])
    pg = {} if isinstance(d, list) else d.get("pagination", {})
    return items, pg

def _id(s): return s.get("sandboxId") or s.get("id", "?")
def _state(s): return (s.get("status") or {}).get("state", "?")
def _img(s):
    uri = (s.get("image") or {}).get("uri", "") if isinstance(s.get("image"), dict) else str(s.get("image") or "")
    return uri.split("/")[-1].rsplit(":", 1)[0] if uri else "-"

def _cmd_exec(sid, port, cmd):
    r = execd(sid, port, "POST", "/command", json={"command": cmd})
    if r.status_code != 200: return None
    text = ""
    for line in r.text.strip().split("\n"):
        if not line: continue
        try:
            ev = __import__("json").loads(line)
            if ev.get("type") == "stdout": text += ev.get("text", "") + "\n"
        except: pass
    return text

# sidebar
page = st.sidebar.radio("导航", ["📋 总览", "⚙️ 配置"], label_visibility="collapsed")
if "page_prev" not in st.session_state: st.session_state.page_prev = page
if page != st.session_state.page_prev: st.session_state.subpage = None
st.session_state.page_prev = page
sandboxes, pagination = fetch(st.session_state.sb_page, st.session_state.sb_size)

def show_detail(sid):
    r = api(f"/sandboxes/{sid}")
    if r.status_code != 200: st.error(f"get fail: {r.text}"); return
    sb = r.json()
    state = _state(sb)
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("状态", state); c2.metric("镜像", _img(sb))
    limits = sb.get("resourceLimits", {}) or {}
    c3.metric("CPU", limits.get("cpu", "-")); c4.metric("内存", limits.get("memory", "-"))
    st.divider()
    ac = st.columns(4)
    if state == "Paused" and ac[0].button("▶️ 恢复"): api(f"/sandboxes/{sid}/resume", "POST"); st.rerun()
    if state == "Running" and ac[1].button("⏸️ 暂停"): api(f"/sandboxes/{sid}/pause", "POST"); st.rerun()
    if ac[2].button("🔄 续期"): api(f"/sandboxes/{sid}/renew-expiration", "POST"); st.toast("已续期")
    if ac[3].button("🗑️ 删除"): api(f"/sandboxes/{sid}", "DELETE"); st.session_state.subpage = None; st.rerun()
    st.divider()
    with st.expander("⚡ 代码执行"):
        lang = st.selectbox("语言", ["python","bash","javascript","go"], key=f"lang_{sid}")
        code = st.text_area("代码", height=150, key=f"code_{sid}")
        if st.button("执行", key=f"run_{sid}"):
            runtimes = {"python":"python -c","bash":"bash -c","javascript":"node -e","go":"go run"}
            cmd = f'{runtimes[lang]} "{code.replace(chr(34), chr(92)+chr(34))}"'
            with st.spinner("..."):
                rr = execd(sid, 44772, "POST", "/command", json={"command": cmd})
            if rr.status_code == 200:
                for line in rr.text.strip().split("\n"):
                    if not line: continue
                    try:
                        ev = __import__("json").loads(line)
                        t = ev.get("type")
                        if t == "stdout": st.code(ev.get("text",""), language=lang)
                        elif t == "stderr": st.code(ev.get("text",""), language=None)
                        elif t == "error": st.error(str(ev.get("error","")))
                    except: st.text(line)
                st.success("done")
            else: st.error(f"fail: {rr.text[:300]}")
    with st.expander("📁 文件浏览"):
        ck = f"fcwd_{sid}"
        if ck not in st.session_state: st.session_state[ck] = "/workspace"
        cwd = st.session_state[ck]
        nc1,nc2 = st.columns([3,1])
        nn = nc1.text_input("新文件", placeholder="name", key=f"nf_{sid}")
        if nc2.button("➕ 新建", key=f"nfb_{sid}"):
            if nn: execd(sid,44772,"POST","/command",json={"command": f"touch {os.path.join(cwd, nn)}"}); st.rerun()
        st.caption(f"📂 {cwd}")
        rl = execd(sid,44772,"GET","/directories/list", params={"path": cwd})
        if rl.status_code == 200:
            entries = rl.json()
            if isinstance(entries, list):
                if cwd != "/":
                    if st.button("📁 ..", key=f"up_{sid}"):
                        st.session_state[ck] = os.path.dirname(cwd); st.rerun()
                for e in entries:
                    nm = os.path.basename(e.get("path","?"))
                    epath = e.get("path","")
                    is_dir = e.get("type") == "directory"
                    c1,c2,c3 = st.columns([6,1,1])
                    with c1:
                        if st.button(f"{'📁' if is_dir else '📄'} {nm}", key=f"nv_{sid}_{epath}"):
                            if is_dir: st.session_state[ck] = epath; st.rerun()
                            else:
                                txt = _cmd_exec(sid, 44772, f"base64 < {epath}")
                                # ponytail: base64 decode for binary safety
                                try: txt = base64.b64decode(txt.replace("\n","").replace("\r","")).decode(errors="replace") if txt else ""
                                except: txt = txt or ""
                                st.session_state[f"fct_{sid}"] = txt
                                st.session_state[f"fpt_{sid}"] = epath; st.rerun()
                    with c2:
                        if not is_dir and st.button("🗑️", key=f"dl_{sid}_{epath}"):
                            execd(sid,44772,"POST","/command",json={"command": f"rm -f {epath}"}); st.rerun()
                fp = st.session_state.get(f"fpt_{sid}")
                if fp:
                    st.divider(); st.caption(f"📝 {fp}")
                    cnt = st.text_area("内容", value=st.session_state.get(f"fct_{sid}",""), height=300, key=f"ed_{sid}")
                    c1,c2 = st.columns(2)
                    if c1.button("💾 保存", key=f"sv_{sid}"):
                        # ponytail: base64 encode for binary safety
                        b64 = base64.b64encode(cnt.encode()).decode()
                        execd(sid,44772,"POST","/command",json={"command": f"echo '{b64}' | base64 -d > {fp}"})
                        st.session_state[f"fct_{sid}"] = cnt; st.toast("saved"); st.rerun()
                    if c2.button("❌ 关闭", key=f"cl_{sid}"):
                        del st.session_state[f"fpt_{sid}"]; del st.session_state[f"fct_{sid}"]; st.rerun()
            else: st.json(entries)
        else: st.warning(f"list fail: {rl.text[:300]}")
    # ponytail: snapshots
    with st.expander("📸 快照"):
        if st.button("📷 创建快照", key=f"snap_create_{sid}"):
            r = api(f"/sandboxes/{sid}/snapshots", "POST")
            if r.status_code in (200,201,202): st.toast("快照创建中...")
            else: st.error(f"创建快照失败: {r.text[:300]}")
        # list snapshots
        sr = api("/snapshots")
        if sr.status_code == 200:
            snaps = sr.json() if isinstance(sr.json(), list) else sr.json().get("items", [])
            for sn in snaps:
                # ponytail: filter snapshots originated from this sandbox (best-effort)
                sn_id = sn.get("originalSandboxId") or sn.get("sandboxId") or ""
                if sn_id and sn_id != sid: continue
                sn_full = sn.get("snapshotId") or sn.get("id", "?")
                c1,c2 = st.columns([4,1])
                c1.caption(f"{sn_full[:20]}... ({sn.get('status','?')})")
                if c2.button("♻️ 恢复", key=f"snap_restore_{sn_full[:12]}"):
                    r2 = api("/sandboxes", "POST", json={"snapshotId": sn_full})
                    if r2.status_code in (200,201,202): st.toast("已从快照创建沙箱"); st.rerun()
                    else: st.error(f"恢复失败: {r2.text[:200]}")
        else: st.caption("无法获取快照列表")
    with st.expander("🔧 进程管理"):
        if st.button("📋 列出进程", key=f"ps_{sid}"):
            out = _cmd_exec(sid, 44772, "ps aux --sort=-%cpu | head -20")
            st.code(out or "无进程数据", language="bash")
        kill_pid = st.text_input("PID", key=f"kp_{sid}")
        if st.button("💀 Kill", key=f"kill_{sid}") and kill_pid:
            rk = execd(sid, 44772, "POST", "/command", json={"command": f"kill -9 {kill_pid}"})
            if rk.status_code == 200: st.toast(f"Sent SIGKILL to {kill_pid}")
            else: st.error(rk.text[:200])
    with st.expander("原始数据"): st.json(sb)
    with st.expander("诊断日志"):
        scope = st.text_input("Scope", key="log_scope")
        if st.button("获取日志"):
            lp = f"/sandboxes/{sid}/diagnostics/logs"
            if scope: lp += f"?scope={scope}"
            lr = api(lp)
            if lr.status_code == 200:
                if "text/plain" in (lr.headers.get("content-type") or ""):
                    st.code(lr.text[:20000], language="log")
                else:
                    ld = lr.json()
                    if c := ld.get("content"): st.code(c[:20000], language="log")
                    elif u := ld.get("url"): st.markdown(f"[下载]({u})")
                    else: st.info("no logs")
            else: st.warning(lr.text)

# pages
if page == "📋 总览":
    sp = st.session_state.subpage
    if sp and sp.startswith("detail:"):
        sid = sp.split(":",1)[1]
        st.header("Sandbox 详情")
        st.caption(f"ID: `{sid[:16]}...`")
        if st.button("← 返回总览"): st.session_state.subpage = None; st.rerun()
        show_detail(sid)
    elif sp == "create":
        st.header("创建 Sandbox")
        image = st.text_input("镜像", value="agentscope/runtime-sandbox-icbc_skill_scope:latest")
        timeout = st.number_input("超时(秒)", value=300, min_value=10)
        c1,c2 = st.columns(2)
        cpu = c1.text_input("CPU", value="1")
        mem = c2.text_input("内存", value="512Mi")
        ep = st.text_input("Entrypoint", value="sleep infinity")
        # ponytail: env vars
        env_raw = st.text_area("环境变量", placeholder="KEY1=val1\nKEY2=val2", height=80)
        c3,c4 = st.columns(2)
        if c3.button("创建", type="primary"):
            body = {"image":{"uri":image},"timeout":timeout,"entrypoint":ep.split()}
            if st.session_state.osb_proxy: body["useProxy"] = True
            if cpu or mem: body["resourceLimits"] = {"cpu":cpu,"memory":mem}
            # ponytail: parse env
            if env_raw.strip():
                env = {}
                for line in env_raw.strip().split("\n"):
                    if "=" in line:
                        k, _, v = line.partition("=")
                        env[k.strip()] = v.strip()
                if env: body["env"] = env
            r = api("/sandboxes","POST",json=body)
            if r.status_code in (200,201,202): d=r.json(); st.success(f"OK {_id(d)}"); st.json(d)
            else: st.error(f"fail ({r.status_code}): {r.text}")
        if c4.button("← 返回总览"): st.session_state.subpage = None; st.rerun()
    else:
        st.header("Sandbox 列表")
        # ponytail: auto-refresh
        if st.checkbox("🔄 自动刷新 (5s)", key="auto_refresh"):
            time.sleep(5); st.rerun()
        if st.button("➕ 创建 Sandbox", use_container_width=True): st.session_state.subpage = "create"; st.rerun()
        if not sandboxes: st.info("暂无 sandbox")
        else:
            cols = st.columns([3,2,2,1])
            for h,c in zip(["ID","状态","镜像","操作"],cols): c.caption(f"**{h}**")
            for s in sandboxes:
                sid = _id(s); state = _state(s)
                emoji = {"Running":"🟢","Pending":"🟡","Paused":"⏸️","Terminated":"⚫","Failed":"🔴"}.get(state,"❓")
                c1,c2,c3,c4 = st.columns([3,2,2,1])
                c1.write(sid[:12]+"...")
                c2.write(f"{emoji} {state}")
                c3.write(_img(s))
                if c4.button("🔍", key=f"dtl_{sid}"): st.session_state.subpage = f"detail:{sid}"; st.rerun()
            # ponytail: pagination
            total = pagination.get("totalItems", len(sandboxes))
            total_pages = pagination.get("totalPages", 1)
            st.caption(f"第 {st.session_state.sb_page}/{total_pages} 页 · 共 {total} 个")
            pc1,pc2,pc3 = st.columns([1,2,1])
            if pc1.button("← 上一页") and st.session_state.sb_page > 1:
                st.session_state.sb_page -= 1; st.rerun()
            pc2.write("")
            if pc3.button("下一页 →") and st.session_state.sb_page < total_pages:
                st.session_state.sb_page += 1; st.rerun()

elif page == "⚙️ 配置":
    st.header("配置")
    st.text_input("API Base", key="osb_base", on_change=_save_config)
    st.text_input("API Key", key="osb_key", type="password", on_change=_save_config)
    st.checkbox("使用代理", key="osb_proxy", on_change=_save_config)
    st.caption("配置持久化到 ~/.opensandbox-viz.json，重启不丢")
    if st.button("🔄 恢复默认"):
        st.session_state.osb_base = BASE
        st.session_state.osb_key = KEY
        st.session_state.osb_proxy = False
        _save_config()
        st.rerun()
