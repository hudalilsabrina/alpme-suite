# alpme-suite

Registrasi otomatis + mint API key untuk **alpme.com** (AI gateway).

- Signup cuma butuh email + password — **tanpa captcha, tanpa verifikasi email**
- Promo `ALP27` → **Ultra plan, 180 hari** ($300 / 5 jam · $2.100 / minggu · maks 15 key)
- Key di-mint lewat `POST /api/keys` dengan header `X-Alpme-Client: vscode`
- Inference: `https://alpme.com/v1` (OpenAI-compatible)

---

## Status penting

> ⚠️ Per 25 Okt 2026, **inference alpme sedang 503 `server_overloaded` untuk semua model** —
> bukan karena akun, bukan karena promo. Signup dan mint key tetap jalan normal.
> Node `alpme` di 9router sengaja di-park (`isActive: false`) sampai upstream pulih.

---

## Install

```bash
pip install -r requirements.txt      # kosong — cuma stdlib
export TEMPIK_BASE="https://mail.example.com/api"
```

---

## Pakai

```bash
# satu akun + key
python3 main.py register --promo ALP27 --ref ariqnetz7-3b6e

# batch (rotasi IP otomatis per akun lewat bridge)
python3 alpme_farm.py -n 20 --gap 3

# tanpa rotasi IP (kalau bridge mati)
python3 alpme_farm.py -n 5 --no-rotate

# tanpa inject ke 9router
python3 alpme_farm.py -n 5 --no-9router
```

Output:

| File | Isi |
|---|---|
| `accounts.txt` | `email:password` per baris |
| `keys.txt` | `sk_live_*` per baris |
| `farm.log` | log lengkap |

---

## CLI lain

```bash
python3 main.py models --key sk_live_xxx     # 40+ model
python3 main.py test --key sk_live_xxx       # tes 4 model frontier
python3 main.py login -e a@b.c -p pass --mint
python3 main.py quota -e a@b.c -p pass
```

---

## Batasan yang ditemukan

| Batasan | Detail |
|---|---|
| `ip_taken` | Maks ~2–3 akun per IP. **Wajib rotasi IP** — suite ini otomatis panggil `POST /__new_session` ke bridge sebelum tiap signup |
| `desktop_only` | `POST /api/keys` ditolak 403 tanpa header `X-Alpme-Client: vscode` |
| `max_keys: 15` | Maks 15 key per akun |
| `server_overloaded` | 503 platform-wide saat upstream penuh |

---

## Model yang tersedia

Frontier: `gpt-6-astra`, `gpt-6.1-sol`, `claude-opus-5-5`, `claude-fable-5-1`,
`gemini-4-argon`, `gemini-3.1-pro`, `grok-4.7`, `kimi-k3.1-pro`, `deepseek-v4-pro`,
`glm-5.3`, `qwen3.8-max`, `minimax-m3`, `hy4-preview` — total 40+.

---

## 9router

Node otomatis dibuat: `openai-compatible-chat-alpme`, prefix **`alpme`**.

```bash
curl http://127.0.0.1:20127/v1/chat/completions \
  -H "Authorization: Bearer <9router-key>" \
  -d '{"model":"alpme/gpt-6-astra","messages":[{"role":"user","content":"Halo"}]}'
```

Aktifkan lagi setelah upstream pulih:

```python
# isActive: true pada providerNodes id=openai-compatible-chat-alpme
```

---

## Etika

Suite ini untuk eksperimen pribadi. Membagikan key hasil farm ke publik
melanggar ToS alpme dan berisiko akun di-suspend massal.
