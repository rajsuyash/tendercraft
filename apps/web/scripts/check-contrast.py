import json,sys
t = json.load(open("design/tokens.json"))["color"]
def lum(h):
    h=h.lstrip('#'); r,g,b=[int(h[i:i+2],16)/255 for i in (0,2,4)]
    f=lambda c: c/12.92 if c<=0.03928 else ((c+0.055)/1.055)**2.4
    return 0.2126*f(r)+0.7152*f(g)+0.0722*f(b)
def cr(a,b):
    l1,l2=sorted([lum(a),lum(b)],reverse=True); return (l1+0.05)/(l2+0.05)
pairs=[("text","surface"),("text","surface-alt"),("text-muted","surface"),("text-muted","surface-alt"),
 ("primary","surface"),("primary","surface-alt"),("primary","primary-tint"),("on-primary","primary"),
 ("success","success-bg"),("danger","danger-bg"),("warning","warning-bg"),("info","info-bg"),
 ("success","surface"),("danger","surface"),("warning","surface"),("info","surface"),
 ("success","surface-alt"),("danger","surface-alt"),("warning","surface-alt")]
fails=[(f,b,cr(t[f],t[b])) for f,b in pairs if cr(t[f],t[b])<4.5]
for f,b in pairs: print(f"  {f+' on '+b:34} {cr(t[f],t[b]):5.2f}")
print("\nGLB-D1:", "FAIL "+str(fails) if fails else "PASS — all 19 pairs >= 4.5:1")
sys.exit(1 if fails else 0)
