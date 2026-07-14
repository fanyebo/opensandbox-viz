"""OpenSandbox Dashboard"""
import streamlit as st, httpx, os

st.set_page_config(page_title="OpenSandbox Viz", page_icon="📦", layout="wide")

KEY = os.getenv("OSB_API_KEY", "dev-api-key-change-in-production")
BASE = os.getenv("OSB_API_BASE", "http://localhost:8080/v1")

if "osb_key" not in st.session_state: st.session_state.osb_key = KEY
if "osb_base" not in st.session_state: st.session_state.osb_base = BASE
if "osb_proxy" not in st.session_state: st.session_state.osb_proxy = False
if "subpage" not in st.session_state: st.session_state.subpage = None

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

def fetch():
    r = api("/sandboxes")
    if r.status_code == 200:
        d = r.json(); return d if isinstance(d, list) else d.get("items", [])
    return []

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
            if ev.get("type") == "stdout": text += ev.get("text", "")
        except: pass
    return text

# sidebar
page = st.sidebar.radio("导航", ["📋 总览", "⚙️ 配置"], label_visibility="collapsed")
if "page_prev" not in st.session_state: st.session_state.page_prev = page
if page != st.session_state.page_prev: st.session_state.subpage = None  # ponytail: clear subpage on sidebar nav
st.session_state.page_prev = page
sandboxes = fetch()

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
                                txt = _cmd_exec(sid, 44772, f"cat {epath}")
                                st.session_state[f"fct_{sid}"] = txt or ""
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
                        safe = cnt.replace("'", "'\\''").replace("`", "\\`")
                        execd(sid,44772,"POST","/command",json={"command": f"cat > {fp} << 'EOF'\n{safe}\nEOF"})
                        st.session_state[f"fct_{sid}"] = cnt; st.toast("saved"); st.rerun()
                    if c2.button("❌ 关闭", key=f"cl_{sid}"):
                        del st.session_state[f"fpt_{sid}"]; del st.session_state[f"fct_{sid}"]; st.rerun()
            else: st.json(entries)
        else: st.warning(f"list fail: {rl.text[:300]}")
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
        c3,c4 = st.columns(2)
        if c3.button("创建", type="primary"):
            body = {"image":{"uri":image},"timeout":timeout,"entrypoint":ep.split()}
            if st.session_state.osb_proxy: body["useProxy"] = True
            if cpu or mem: body["resourceLimits"] = {"cpu":cpu,"memory":mem}
            r = api("/sandboxes","POST",json=body)
            if r.status_code in (200,201,202): d=r.json(); st.success(f"OK {_id(d)}"); st.json(d)
            else: st.error(f"fail ({r.status_code}): {r.text}")
        if c4.button("← 返回总览"): st.session_state.subpage = None; st.rerun()
    else:
        st.header("Sandbox 列表")
        if st.button("➕ 创建 Sandbox", use_container_width=True): st.session_state.subpage = "create"; st.rerun()
        if not sandboxes: st.info("暂无 sandbox")
        else:
            cols = st.columns([2,2,2,1,1,1])
            for h,c in zip(["ID","状态","镜像","CPU","内存","操作"],cols): c.caption(f"**{h}**")
            for s in sandboxes:
                sid = _id(s); state = _state(s)
                emoji = {"Running":"🟢","Pending":"🟡","Paused":"⏸️","Terminated":"⚫","Failed":"🔴"}.get(state,"❓")
                rl = (s.get("resourceLimits") or {})
                c1,c2,c3,c4,c5,c6 = st.columns([2,2,2,1,1,1])
                c1.write(sid[:12]+"...")
                c2.write(f"{emoji} {state}")
                c3.write(_img(s))
                c4.write(rl.get("cpu","-"))
                c5.write(rl.get("memory","-"))
                if c6.button("🔍", key=f"dtl_{sid}"): st.session_state.subpage = f"detail:{sid}"; st.rerun()
            st.caption(f"共 {len(sandboxes)} 个")

elif page == "⚙️ 配置":
    st.header("配置")
    st.text_input("API Base", key="osb_base", value=st.session_state.osb_base)
    st.text_input("API Key", key="osb_key", value=st.session_state.osb_key, type="password")
    st.checkbox("使用代理", key="osb_proxy", value=st.session_state.osb_proxy)
    st.caption("无需重启，直接生效")
    if st.button("🔄 恢复默认"):
        st.session_state.osb_base = BASE
        st.session_state.osb_key = KEY
        st.rerun()
