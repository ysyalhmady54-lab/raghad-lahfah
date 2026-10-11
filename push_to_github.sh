#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v git >/dev/null 2>&1; then
  echo "Git غير مثبت. نفّذ: pkg install git -y"
  exit 1
fi

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git init
fi

git branch -M main
git add .
if ! git diff --cached --quiet; then
  git commit -m "Build Raghad anonymous letters website"
else
  echo "لا توجد تغييرات جديدة لإضافتها."
fi

if ! git remote get-url origin >/dev/null 2>&1; then
  echo ""
  echo "أنشئ مستودعًا فارغًا في GitHub أولًا، ثم الصق رابط المستودع هنا."
  read -r -p "GitHub repository URL (HTTPS or SSH): " REPO_URL
  if [[ -z "${REPO_URL// }" ]]; then
    echo "لم تدخل رابط المستودع. لم يتم الرفع."
    exit 1
  fi
  git remote add origin "$REPO_URL"
fi

echo "سيتم رفع المشروع إلى GitHub الآن..."
git push -u origin main
echo "تم رفع الملفات إلى GitHub بنجاح."
