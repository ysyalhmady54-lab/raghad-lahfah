(() => {
  const form = document.getElementById('messageForm');
  const textarea = document.getElementById('messageBody');
  const count = document.getElementById('charCount');
  const status = document.getElementById('formStatus');
  const sendButton = document.getElementById('sendButton');
  const shareButton = document.getElementById('shareLink');
  const toast = document.getElementById('toast');
  let mood = 'رسالة من القلب';
  let toastTimer;

  document.getElementById('year').textContent = new Date().getFullYear();

  function showToast(message) {
    toast.textContent = message;
    toast.classList.add('show');
    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(() => toast.classList.remove('show'), 2800);
  }

  document.querySelectorAll('.mood-chip').forEach((button) => {
    button.addEventListener('click', () => {
      document.querySelectorAll('.mood-chip').forEach((item) => item.classList.remove('active'));
      button.classList.add('active');
      mood = button.dataset.mood || 'رسالة من القلب';
    });
  });

  textarea.addEventListener('input', () => {
    count.textContent = `${textarea.value.length} / 1200`;
    if (!status.hidden) {
      status.hidden = true;
      status.className = 'form-status';
    }
  });

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const body = textarea.value.trim();
    if (body.length < 2) {
      textarea.focus();
      setStatus('اكتب رسالتك أولًا، حتى لو كانت كلمة بسيطة 🤍', 'error');
      return;
    }
    sendButton.disabled = true;
    sendButton.querySelector('span').textContent = 'جاري إيصال رسالتك…';
    try {
      const response = await fetch('/api/messages', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ body, mood }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || 'تعذّر إرسال الرسالة الآن. حاول مرة ثانية.');
      setStatus(data.message || 'وصلت رسالتك بأمان. شكرًا لأنك شاركت ما في قلبك 🤍', 'success');
      form.reset();
      mood = 'رسالة من القلب';
      document.querySelectorAll('.mood-chip').forEach((item) => item.classList.toggle('active', item.dataset.mood === mood));
      count.textContent = '0 / 1200';
      showToast('وصلت رسالتك 🤍');
    } catch (error) {
      setStatus(error.message || 'تعذّر إرسال الرسالة. تأكد من اتصال الإنترنت وحاول مجددًا.', 'error');
    } finally {
      sendButton.disabled = false;
      sendButton.querySelector('span').textContent = 'إرسال الرسالة بسرية';
    }
  });

  function setStatus(message, kind) {
    status.textContent = message;
    status.className = `form-status ${kind}`;
    status.hidden = false;
  }

  shareButton.addEventListener('click', async () => {
    const shareData = {
      title: 'مساحة رغد | رسالة مجهولة',
      text: 'عندك كلمة في قلبك؟ اكتب رسالة إلى رغد بدون ما تكتب اسمك 🤍',
      url: `${window.location.origin}/raghad`,
    };
    try {
      if (navigator.share) await navigator.share(shareData);
      else {
        await navigator.clipboard.writeText(shareData.url);
        showToast('تم نسخ رابط الرسائل 🤍');
      }
    } catch (error) {
      if (error.name !== 'AbortError') {
        try {
          await navigator.clipboard.writeText(shareData.url);
          showToast('تم نسخ رابط الرسائل 🤍');
        } catch {
          showToast(shareData.url);
        }
      }
    }
  });

  const revealItems = document.querySelectorAll('.reveal');
  if ('IntersectionObserver' in window) {
    const observer = new IntersectionObserver((entries, instance) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add('visible');
          instance.unobserve(entry.target);
        }
      });
    }, { threshold: 0.13 });
    revealItems.forEach((item) => observer.observe(item));
  } else revealItems.forEach((item) => item.classList.add('visible'));
})();
