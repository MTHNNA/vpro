#!/bin/bash
# =============================================
# سكريبت إصلاح مشاكل يوتيوب وإنستقرام
# شغّله مرة واحدة بعد رفع الملفات
# =============================================

echo "🔄 جاري تحديث yt-dlp..."
pip install --upgrade "yt-dlp @ git+https://github.com/yt-dlp/yt-dlp.git" --break-system-packages 2>/dev/null \
  || pip install --upgrade yt-dlp

echo "✅ إصدار yt-dlp الحالي:"
yt-dlp --version

echo ""
echo "🔍 اختبار يوتيوب..."
yt-dlp --simulate --quiet "https://www.youtube.com/watch?v=dQw4w9WgXcQ" \
  --extractor-args "youtube:player_client=mweb,ios" \
  && echo "✅ يوتيوب يعمل" || echo "❌ يوتيوب فيه مشكلة"

echo ""
echo "🔍 اختبار إنستقرام (رابط عام)..."
yt-dlp --simulate --quiet "https://www.instagram.com/p/CUbXQ6JKiBa/" \
  --add-headers "User-Agent:Mozilla/5.0 (iPhone; CPU iPhone OS 17_5_1 like Mac OS X) AppleWebKit/605.1.15 Mobile/21F90 Instagram 341.0.0.36.98" \
  && echo "✅ إنستقرام يعمل" || echo "⚠️ إنستقرام يحتاج cookies"

echo ""
echo "🎉 انتهى! الآن شغّل البوت"
