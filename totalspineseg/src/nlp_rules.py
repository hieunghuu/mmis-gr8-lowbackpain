# -*- coding: utf-8 -*-
"""Module rule trich xuat nhan tu ghi chu bac si X-quang (README muc 5).

Pipeline 6 buoc:
  1. chuan hoa van ban (chu thuong, sua loi chinh ta, chuan hoa ten tang -> <L4-L5>)
  2. tach cau (xuong dong, dau cham, //, ;)
  3. gan tang cho cau (moi tang trong cau; ke thua cau truoc; UNSPEC)
  4. nhan dien benh bang tu dien regex
  5. phu dinh kieu NegEx (pham vi trong doan, cat o but/however/...)
  6. muc do va ben

Ham chinh: extract(note) -> (findings: list[dict], sentences: list[dict])
"""
import re
from collections import Counter

# ----------------------------------------------------------------- 1. chuan hoa
# Loi chinh ta gap trong tap dev (dem so lan sua o TYPO_HITS)
TYPO_FIXES = {
    r"\btehcal\b": "thecal", r"\bthecla\b": "thecal", r"\btheca\b": "thecal",
    r"\bcompres+i+ng\b": "compressing", r"\bcompres+ion\b": "compression",
    r"\bcomprssing\b": "compressing", r"\bcompresing\b": "compressing",
    r"\bcompressng\b": "compressing", r"\babit+ing\b": "abutting",
    r"\bencr[ao]+ching\b": "encroaching", r"\bencorching\b": "encroaching",
    r"\bnerr+ve\b": "nerve", r"\bnerveroots?\b": "nerve roots", r"\bnevre\b": "nerve",
    r"\bnot?red\b": "noted", r"\bnoted ar\b": "noted at", r"\bnotedat\b": "noted at",
    r"\bdif+use\b": "diffuse", r"\bbulgs\b": "bulges", r"\bbuldge\b": "bulge",
    r"\bprotusion\b": "protrusion", r"\bprotrsuion\b": "protrusion",
    r"\bsequea?trated\b": "sequestrated", r"\bveretbral\b": "vertebral",
    r"\bfracgement\b": "fragment",
    r"\bpara central\b": "paracentral", r"\bpara median\b": "paramedian",
    r"\bforamens\b": "foramina",
    r"\bspondylolithesis\b": "spondylolisthesis", r"\bspondylolysthesis\b": "spondylolisthesis",
    r"\bhaemangioma\b": "hemangioma", r"\bhemngioma\b": "hemangioma",
    r"\bhyper?a?tophy\b": "hypertrophy", r"\bhyperatrophy\b": "hypertrophy",
    r"\bligamnetum\b": "ligamentum",
    r"\bmultilevels\b": "multilevel", r"\bmultlevel\b": "multilevel", r"\bnot?iceably\b": "noticeably",
    r"\bheniation\b": "herniation", r"\bherniaton\b": "herniation",
    r"\bmusclespasm\b": "muscle spasm", r"\bmuscle spam\b": "muscle spasm",
    r"\bfeatrure\b": "feature", r"\badquate\b": "adequate",
    r"\bend\s?palte": "endplate", r"\bmodec\b": "modic", r"\birrigular\b": "irregular",
    r"\bsch[a-z]*r?l\w*\s+nod\w*": "schmorl nodes", r"\bnoetd\b": "noted",
    r"\bchn?a+nges\b": "changes",
}
TYPO_HITS = Counter()

_LV_PART2 = {"s": "S1", "s1": "S1"}
_END = r"(?=\b|levels?\b)"                                   # cho phep dinh chu: l5/s1levels
LEVEL_RE = re.compile(
    rf"\b(t12|l[1-5])\s*(?:-|/|\\|–)\s*(l?[1-5]|s1?){_END}"   # L4-L5, L4/5, L5/S1, L5-S
    rf"|\b(t12|l[1-5])\s?(l[1-5]|s1){_END}",                   # L4L5, L5S1
    re.I)
VALID_LEVELS = ["T12-L1", "L1-L2", "L2-L3", "L3-L4", "L4-L5", "L5-S1"]


def _canon_level(a, b):
    a = a.upper()
    b = b.lower()
    if b in _LV_PART2:
        b = "S1"
    elif b.isdigit():
        b = ("L" if a.startswith("L") or a == "T12" else a[0]) + b
        if a == "T12" and b == "L1":
            b = "L1"
    else:
        b = b.upper()
    lv = f"{a}-{b}"
    return lv if lv in VALID_LEVELS else None


def normalize(text):
    t = text.replace("\r", "\n").lower()
    for pat, rep in TYPO_FIXES.items():
        def _fix(m, pat=pat, rep=rep):
            if m.group(0) != rep:            # chi dem khi tu thuc su bi doi
                TYPO_HITS[pat] += 1
            return rep
        t = re.sub(pat, _fix, t)

    def _lv(m):
        a, b = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
        lv = _canon_level(a, b)
        return f" <{lv}> " if lv else m.group(0)

    t = LEVEL_RE.sub(_lv, t)
    # dai tang: <L3-L4> to <L5-S1>  -> liet ke du
    def _range(m):
        i, j = VALID_LEVELS.index(m.group(1)), VALID_LEVELS.index(m.group(2))
        return " " + " ".join(f"<{x}>" for x in VALID_LEVELS[min(i, j):max(i, j) + 1]) + " "
    t = re.sub(r"<([A-Z0-9-]+)>\s*(?:to|till|until|-)\s*<([A-Z0-9-]+)>", _range, t)
    return re.sub(r"[ \t]+", " ", t)


# ----------------------------------------------------------------- 2. tach cau
def split_sentences(t):
    parts = re.split(r"\n+|//+|;|(?<!\d)\.(?!\d)", t)
    out = []
    for p in parts:
        p = re.sub(r"^[\s\-–•*:]+", "", p).strip(" ,")
        if p:
            out.append(p)
    return out


# ----------------------------------------------------------------- 4. tu dien benh
VERB_COMP = r"(?:compress\w*|indent\w*|effac\w*|displac\w*|impinge?\w*|encroach\w*|press\w* (?:on|upon)|deform\w*)"
THECAL = r"(?:thecal|dural)\s+sac"
# "exit nerve canal" la lo lien hop, khong phai re than kinh
ROOT = r"(?:(?:exit(?:ing)?|travers\w*|descending)\s+)?(?:[lst]\d\s+)?nerve\s+roots?|exit(?:ing)?\s+nerves?(?!\s+canal)"
# "lateral recess" (ngach ben) thuoc ong song, KHONG phai lo lien hop (README 5.4.1)
FORAMEN = (r"(?:neural\s+|intervertebral\s+|neuro\s?)?foram\w*"
           r"|exit(?:ing)?\s+(?:neural\s+|nerve\s+)?canals?|neural\s+canals?")

# Moi benh: danh sach (regex, kieu). kieu "obj": can dong tu chen ep trong cung doan.
FINDINGS = {
    "disc_bulge": [r"\bbulg\w*"],
    "disc_protrusion": [r"\bprotru\w*"],
    "disc_herniation": [r"\bherniat\w*", r"\bextru\w*", r"\bsequest\w*", r"detached\s+disc"],
    "annular_tear": [r"annular\s+(?:tear|fissure)", r"torn\s+annul\w*", r"annul\w*\s+(?:tear|fissure)",
                     r"(?:hyperintense|high)\s+(?:t2\s+)?signal\b[^.]*annul\w*"],
    # "dissicating / dissecating / disscating / discating / dissicaring disc material" (~35 lan
    # trong dev) = desiccating; mau khong khop "disc at", "discal"
    "disc_desiccation": [r"desiccat\w*", r"dehydrat\w*", r"\bdi(?:s+[ie]?c+|sc)a[tr]\w*",
                         r"degenerat\w*\s+(?:dis[ck]|changes? of the dis[ck])",
                         r"loss of (?:the )?(?:normal )?(?:t2 )?(?:high )?signal"],
    "spinal_canal_stenosis": [r"canal\s+stenosis", r"stenosis of (?:the )?(?:spinal )?canal",
                              r"narrow\w*\s+(?:of\s+)?(?:the\s+)?(?:spinal\s+|central\s+)?canal",
                              r"(?:spinal|central)\s+(?:canal\s+)?stenosis", r"\bcanal\b[^.]*\bnarrow\w*",
                              # ngach ben: chi tinh khi co tu chi hep/chen ep, khong tinh "extending to"
                              r"(?:narrow\w*|compress\w*|encroach\w*|stenos\w*)[^.]{0,40}lateral\s+recess",
                              r"lateral\s+recess\w*[^.]{0,20}(?:narrow\w*|stenos\w*)"],
    "muscle_spasm": [r"muscle\s+spasm", r"\bspasm\b", r"straighten\w*[^.]*lordo\w*", r"loss of[^.]*lordo\w*"],
    "spondylolisthesis": [r"\w*listhesis"],
    "endplate_degeneration": [r"end\s?-?plates?\s+(?:degenerat\w*|irregular\w*|changes?|sclero\w*|erosi\w*|defect\w*)",
                              r"\bmodic\b", r"degenerat\w*\s+end\s?-?plates?", r"irregular\s+end\s?-?plates?",
                              r"end\s?-?plates?\s+degenerat\w*"],
    "schmorl_nodes": [r"schmorl\w*"],
    "bone_marrow_lesion": [r"marrow\s+(?:edema|oedema|signal|lesion|change|infiltrat\w*)",
                           r"signal[^.]*\bmarrow", r"\bha?em\w*gioma\w*"],
    "ligamentum_flavum_hypertrophy": [r"(?:ligament\w*\s+)?flav\w*[^.]*hypertroph\w*",
                                      r"hypertroph\w*[^.]*(?:ligament\w*\s+)?flav\w*"],
    "facet_arthropathy": [r"facet\w*[^.]*(?:arthropath\w*|hypertroph\w*|degenerat\w*|arthros\w*|osteoarthr\w*)",
                          r"(?:arthropath\w*|hypertroph\w*|degenerat\w*|arthros\w*)[^.]*facet\w*"],
    "scoliosis": [r"scolio\w*"],
    "tarlov_cyst": [r"tarlov\w*", r"perineural\s+cysts?"],
    "vertebral_fracture": [r"fractur\w*", r"\bwedg\w*", r"collaps\w*"],
    "osteophyte": [r"osteophyt\w*", r"\bspurs?\b"],
    "disc_space_narrowing": [r"narrow\w*\s+(?:of\s+(?:the\s+)?)?(?:inter\s?vertebral\s+)?dis[ck]\s+spaces?",
                             r"dis[ck]\s+spaces?\s+narrow\w*", r"narrowed\s+<[A-Z0-9-]+>"],
}
# Chen ep: doi tuong + dong tu (trong cung doan)
OBJ_FINDINGS = {
    "thecal_sac_compression": THECAL,
    "nerve_root_compression": ROOT,
    "foraminal_stenosis": FORAMEN,
}
GLOBAL_FINDINGS = {"muscle_spasm", "scoliosis"}    # luon UNSPEC, khong ke thua tang

# ----------------------------------------------------------------- 5. phu dinh
NEG_PRE = re.compile(r"\b(?:no|not|without|negative for|free of|neither|nor)\b")
NEG_POST = re.compile(r"\b(?:(?:is|are|was|were)\s+)?(?:not\s+(?:seen|noted|present|identified|detected|evident)|absent|ruled out)\b")
SCOPE_CUT = re.compile(r"\b(?:but|however|although|though|except|while|whereas|apart from)\b")
NORMAL_CUES = [  # phu dinh gian tiep -> (benh, regex)
    ("spinal_canal_stenosis", r"\b(?:adequate|normal|preserved|maintained|patent)\s+(?:spinal\s+|central\s+)?canal"),
    ("spinal_canal_stenosis", r"\bcanal\b[^.]*\b(?:adequate|normal|patent)\b"),
    ("thecal_sac_compression", r"\b(?:adequate|normal|preserved)\s+(?:thecal|dural)\s+sac"),
]
ABUT = r"\babut\w*|\btouch\w*|\bcontact\w*"

# ----------------------------------------------------------------- 6. muc do / ben
SEVERITY = [("severe", r"\b(?:severe\w*|significant\w*|marked\w*|large\w*|largely|gross\w*|critical\w*)\b"),
            ("moderate", r"\bmoderate\w*\b"),
            ("mild", r"\b(?:mild\w*|minimal\w*|minor|small|slight\w*|tiny|subtle)\b")]
SIDE = [("bilateral", r"\b(?:both|bilateral\w*)\b"),
        ("left", r"\b(?:left|lt)\b"),
        ("right", r"\b(?:right|rt)\b"),
        ("central", r"\b(?:central\w*|median)\b")]

LEVEL_TOKEN = re.compile(r"<([A-Z0-9-]+)>")
ROOT_TOKEN = re.compile(r"\b([ls][1-5])\s+(?:exit(?:ing)?\s+)?nerve\s+roots?")
VERT_TOKEN = re.compile(r"\b(t12|l[1-5]|s1)\s+(?:vertebra\w*|body|bodies|end\s?-?plates?)")
LISTHESIS_LV = re.compile(r"\b(l[1-5])\s+(?:over|on)\s+(l[1-5]|s1)\b")


def _segments(s):
    """Cat cau thanh doan theo tu cat pham vi phu dinh. Tra ve [(start, end)]."""
    cuts = [0] + [m.start() for m in SCOPE_CUT.finditer(s)] + [len(s)]
    return [(a, b) for a, b in zip(cuts, cuts[1:]) if b > a]


def _negated(seg, pos):
    """Benh tai vi tri pos trong doan seg co bi phu dinh khong."""
    for m in NEG_PRE.finditer(seg):
        if m.start() < pos:
            return True
    return bool(NEG_POST.search(seg[pos:pos + 60]))


PHRASE_CUT = re.compile(r",|\band\b|\bwith\b|\bassociated\b|\balong\b|:|\(|\)|&")


def _phrase(seg, pos, end):
    """Cum tu rieng cua mot benh: cat o dau phay / and / with / associated ...
    Tranh 'muon nham' muc do / ben cua benh khac trong cung cau."""
    left = max([m.end() for m in PHRASE_CUT.finditer(seg, 0, pos)], default=0)
    right = min([m.start() for m in PHRASE_CUT.finditer(seg, end)], default=len(seg))
    return left, right


def _nearest(text, pos, table):
    best, dist = "unspecified", 10 ** 6
    for name, pat in table:
        for m in re.finditer(pat, text):
            d = abs(m.start() - pos)
            if d < dist:
                best, dist = name, d
    return best


def _attributes(seg, finding, pos, matched):
    """Muc do va ben cua mot benh, chi tim trong cum tu cua no."""
    end = pos + len(matched)
    a, b = _phrase(seg, pos, end)
    side_txt = seg[a:b]
    if finding in OBJ_FINDINGS:
        # muc do lay tu dong tu chi phoi gan nhat dung truoc doi tuong:
        # "mildly compressing the thecal sac and both nerve roots" -> ca hai deu mild
        verbs = [m for m in re.finditer(VERB_COMP + r"|\bnarrow\w*|\bstenos\w*", seg) if m.start() < pos]
        if verbs:
            v = verbs[-1].start()
            sev_txt, sev_pos = seg[max(0, v - 15):end], v - max(0, v - 15)
        else:
            sev_txt, sev_pos = side_txt, pos - a
    else:
        sev_txt, sev_pos = side_txt, pos - a
    severity = _nearest(sev_txt, sev_pos, SEVERITY)
    if finding == "nerve_root_compression" and re.search(r"roots\b|nerves\b", matched) \
            and not re.search(r"\b(?:left|lt|right|rt)\b", side_txt):
        side = "bilateral"                                   # Q11
    else:
        side = _nearest(side_txt, pos - a, SIDE)
    return severity, side


def _finding_hits(seg):
    """Tra ve [(finding, pos, matched_text)] trong mot doan."""
    hits = []
    for f, pats in FINDINGS.items():
        for p in pats:
            m = re.search(p, seg)
            if m:
                hits.append((f, m.start(), m.group(0)))
                break
    has_verb = re.search(VERB_COMP, seg)
    for f, obj in OBJ_FINDINGS.items():
        m = re.search(obj, seg)
        if not m:
            continue
        if f == "foraminal_stenosis" and re.search(r"narrow\w*|stenos\w*|encroach\w*|compress\w*|obliterat\w*", seg):
            hits.append((f, m.start(), m.group(0)))
        elif f != "foraminal_stenosis" and (has_verb or re.search(r"compression", seg)):
            hits.append((f, m.start(), m.group(0)))
        elif re.search(ABUT, seg):                           # Q1: cham != chen ep
            hits.append((f + "|abut", m.start(), m.group(0)))
        elif f != "foraminal_stenosis" and NEG_PRE.search(seg[:m.start()]):
            # cau phu dinh viet thieu: "no significant thecal sac or nerve roots"
            hits.append((f, m.start(), m.group(0)))
    for f, pat in NORMAL_CUES:
        m = re.search(pat, seg)
        if m and not any(h[0] == f for h in hits):
            hits.append((f + "|normal", m.start(), m.group(0)))
    return hits


def extract(note):
    """note (str) -> (findings, sentences)."""
    t = normalize(str(note))
    findings, sentences = [], []
    prev_levels = []
    for sid, s in enumerate(split_sentences(t), 1):
        levels = list(dict.fromkeys(LEVEL_TOKEN.findall(s)))
        m = LISTHESIS_LV.search(s)
        if m and not levels:
            lv = _canon_level(m.group(1), m.group(2))
            levels = [lv] if lv else []
        inherited = False
        if not levels and prev_levels:
            levels, inherited = prev_levels, True
        roots = sorted(set(x.upper() for x in ROOT_TOKEN.findall(s)))
        verts = sorted(set(x.upper() for x in VERT_TOKEN.findall(s)))
        n_before = len(findings)
        for a, b in _segments(s):
            seg = s[a:b]
            for f, pos, matched in _finding_hits(seg):
                forced_neg = False
                if f.endswith("|abut") or f.endswith("|normal"):
                    f, forced_neg = f.split("|")[0], True
                present = not (forced_neg or _negated(seg, pos))
                sev, side = _attributes(seg, f, pos, matched) if present else ("unspecified", "unspecified")
                lvls = ["UNSPEC"] if (f in GLOBAL_FINDINGS or not levels) else levels
                for lv in lvls:
                    findings.append({
                        "sentence_id": sid, "level": lv,
                        "level_inherited": inherited and lv != "UNSPEC",
                        "vertebra": ",".join(verts), "root": ",".join(roots),
                        "finding": f, "present": present,
                        "severity": sev, "side": side,
                        "evidence": s.strip(),
                    })
        # cau co tang that su -> lam moc ke thua cho cau sau
        own = list(dict.fromkeys(LEVEL_TOKEN.findall(s)))
        if own:
            prev_levels = own
        sentences.append({"sentence_id": sid, "text": s, "levels": ",".join(levels),
                          "inherited": inherited, "n_findings": len(findings) - n_before})
    # gop trung (cung tang + benh + present) giu dong dau
    seen, uniq = set(), []
    for f in findings:
        k = (f["level"], f["finding"], f["present"])
        if k not in seen:
            seen.add(k)
            uniq.append(f)
    return uniq, sentences
