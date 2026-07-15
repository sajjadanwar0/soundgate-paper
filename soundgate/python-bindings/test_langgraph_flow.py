class Core:
    def __init__(s): s.released=set();s.cancelled=set();s.pending={};s.rejected=set();s.closed=set()

    def submit(s,r,k,n):
        if r in s.cancelled or r in s.closed: return "refused_cancelled"
        i=(r,k)
        if i in s.released: return "refused_duplicate"
        if i in s.rejected: return "refused_rejected"
        if i in s.pending:  return "held_for_approval"
        if n: s.pending[i]=1; return "held_for_approval"
        s.released.add(i); return "release"

    def decide(s,r,k,a):
        i=(r,k)
        if i not in s.pending:
            if r in s.cancelled or r in s.closed: return "refused_cancelled"
            if i in s.released: return "refused_duplicate"
            if i in s.rejected: return "refused_rejected"
            return "refused_duplicate"
        del s.pending[i]
        if a: s.released.add(i); return "release"
        s.rejected.add(i); return "refused_rejected"
    def cancel(s,r): s.cancelled.add(r); return "ack"

def run_gate():
    srv=socket.socket(); srv.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
    srv.bind(("127.0.0.1",0)); srv.listen(5); port=srv.getsockname()[1]; core=Core()
    def handle(conn):
        rf=conn.makefile("r")
        for line in rf:
            line=line.strip()
            if not line: continue
            q=json.loads(line); op=q["op"]
            if op=="submit": rep={"verdict":core.submit(q["run_id"],q["effect_key"],q.get("needs_approval",False))}
            elif op=="decide": rep={"verdict":core.decide(q["run_id"],q["effect_key"],q["approved"])}
            elif op=="cancel": rep={"verdict":core.cancel(q["run_id"])}
            else: rep={"verdict":"pong"}
            conn.sendall((json.dumps(rep)+"\n").encode())
    def loop():
        while True:
            c,_=srv.accept(); threading.Thread(target=handle,args=(c,),daemon=True).start()
    threading.Thread(target=loop,daemon=True).start(); return port

port=run_gate()
g=GateClient(("127.0.0.1",port))
log=[]

print("=== no-approval effect: runs once, replay deduped ===")
r="thread-1"
print(" first :", mediate_no_approval(g,r,"welcome",lambda:(log.append("welcome"),"ok")[1]))
print(" replay:", mediate_no_approval(g,r,"welcome",lambda:(log.append("welcome"),"ok")[1]))

print("=== approval effect: approve -> runs; reject -> does not ===")
print(" approve:", mediate_with_approval(g,r,"refund",lambda:(log.append("refund"),"ok")[1],
                                         interrupt_fn=lambda _:{"approved":True}, resume_to_approved=lambda p:p["approved"]))
print(" reject :", mediate_with_approval(g,r,"wire",lambda:(log.append("wire"),"ok")[1],
                                         interrupt_fn=lambda _:{"approved":False}, resume_to_approved=lambda p:p["approved"]))

print("=== sibling-leak repair: branch A held for approval, sibling B mediated during the pause ===")
r2="thread-2"
va=g.submit(r2,"branchA_email",True)                       # A: held (paused for approval)
print(" A submit ->", va); assert va=="held_for_approval"
sib=mediate_no_approval(g,r2,"branchB_charge",lambda:(log.append("SIBLING CHARGE"),"ok")[1])  # B during pause
print(" B (sibling) ->", sib)


gA=g.decide(r2,"branchA_email",False)
print(" A decide(reject) ->", gA)

print("\neffects performed:", log)

assert "welcome" in log and log.count("welcome")==1
assert "refund" in log and "wire" not in log
print("OK — approve runs, replay+reject blocked; sibling policy demonstrated")