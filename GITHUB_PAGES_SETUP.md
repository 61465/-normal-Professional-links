# تفعيل النشر على GitHub Pages + Fly.io

الـ workflow مرفوع. تحتاج 3 خطوات يدوية لا يستطيع الـ CLI تنفيذها (تتطلب تسجيل دخول).

---

## الخطوة 1️⃣ — تفعيل GitHub Pages (دقيقة واحدة)

1. افتح https://github.com/61465/professional-links/settings/pages
2. تحت **Build and deployment** → **Source**: اختر **GitHub Actions**
3. احفظ.

الـ workflow اللي رفعته للتو يبني تلقائياً وينشر. تابع التقدم على:
https://github.com/61465/professional-links/actions

بعد ~2 دقيقة سيكون الموقع على:
**https://61465.github.io/professional-links/**

> ⚠️ بدون هذه الخطوة الموقع يرجع 404 لأن Pages معطّل.

---

## الخطوة 2️⃣ — نشر الـ Backend على Fly.io (5 دقائق)

الواجهة وحدها لن تعمل — كل البيانات تجلب من backend. ينشر مرة واحدة:

```powershell
# ثبت flyctl لو مش مثبت
iwr https://fly.io/install.ps1 -useb | iex

# سجل دخول (يفتح المتصفح)
fly auth login

# من جذر المشروع D:\project\mobeface
cd D:\project\mobeface
fly launch --no-deploy --copy-config --name mobeface-api
# لما يسأل عن region اختر fra أو الأقرب لك
# لما يسأل postgres/upstash/sentry: No لكل شيء

# اضبط CORS لدومين Pages
fly secrets set ALLOWED_ORIGINS="https://61465.github.io"

# انشر
fly deploy
```

سيخرج URL مثل: `https://mobeface-api.fly.dev`. اختبره:
```powershell
curl https://mobeface-api.fly.dev/api/health
```
يجب أن يرجع `{"status":"ok"}`.

---

## الخطوة 3️⃣ — اربط الـ frontend بالـ backend (30 ثانية)

1. افتح https://github.com/61465/professional-links/settings/variables/actions
2. اضغط **New repository variable**
3. **Name:** `VITE_API_BASE`
4. **Value:** `https://mobeface-api.fly.dev` (أو الـ URL اللي طلع من fly)
5. احفظ.

ثم أعد تشغيل الـ workflow:
- https://github.com/61465/professional-links/actions
- آخر run → **Re-run all jobs**

بعد ~2 دقيقة الموقع سيعمل بالكامل على:
**https://61465.github.io/professional-links/**

---

## ✅ التحقق النهائي

افتح https://61465.github.io/professional-links/ — يجب أن ترى الإعلانات تتحمّل من Craigslist (eBay سيكون فارغ بسبب 403 من cloud IPs — موضّح في DEPLOYMENT.md).

## 🆘 لو ما اشتغل

| المشكلة | الحل |
|--------|-----|
| 404 على Pages | الخطوة 1 لم تتم — Settings→Pages→Source=GitHub Actions |
| الصفحة تفتح لكن "Backend غير مشغّل" | الخطوة 2 (fly deploy) لم تتم أو الخطوة 3 (var) لم تُحفظ |
| CORS error في console | عدّل `fly secrets set ALLOWED_ORIGINS="https://61465.github.io"` وأعد `fly deploy` |
| الـ assets 404 | الـ workflow فشل — افتح Actions tab وشاهد الـ log |
