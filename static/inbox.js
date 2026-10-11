(() => {
  const loginPanel = document.getElementById('loginPanel');
  const dashboard = document.getElementById('dashboard');
  const loginForm = document.getElementById('loginForm');
  const loginError = document.getElementById('loginError');
  const loginButton = document.getElementById('loginButton');
  const messageList = document.getElementById('messageList');
  const emptyState = document.getElementById('emptyState');
  const totalCount = document.getElementById('totalCount');
  const unreadCount = document.getElementById('unreadCount');
  const filter = document.getElementById('filterMessages');
  const toast = document.getElementById('inboxToast');
  let allMessages = [];
  let toastTimer;

  const escapeText = (value) => String(value ?? '');
  function notify(text) {
    toast.textContent = text;
    toast.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove('show'), 2600);
  }

  async function api(url, options = {}) {
    const response = await fetch(url, { credentials: 'same-origin', ...options, headers: { ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...(options.headers || {}) } });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(data.detail || 'تعذّر تنفيذ الطلب.');
      error.status = response.status;
      throw error;
    }
    return data;
  }

  async function checkSession() {
    try {
      await api('/api/messages');
      loginPanel.hidden = true;
      dashboard.hidden = false;
      await loadMessages();
    } catch (error) {
      if (error.status === 401) {
        loginPanel.hidden = false;
        dashboard.hidden = true;
      } else {
        loginError.textContent = 'تعذّر الاتصال بالخادم. حدّث الصفحة وحاول مرة أخرى.';
        loginError.hidden = false;
      }
    }
  }

  loginForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    loginButton.disabled = true;
    loginButton.firstChild.textContent = 'جارٍ التحقق… ';
    loginError.hidden = true;
    try {
      await api('/api/login', { method: 'POST', body: JSON.stringify({ password: document.getElementById('password').value }) });
      document.getElementById('password').value = '';
      loginPanel.hidden = true;
      dashboard.hidden = false;
      await loadMessages();
    } catch (error) {
      loginError.textContent = error.message || 'تعذّر تسجيل الدخول.';
      loginError.hidden = false;
    } finally {
      loginButton.disabled = false;
      loginButton.firstChild.textContent = 'فتح صندوق الرسائل ';
    }
  });

  document.getElementById('logoutButton').addEventListener('click', async () => {
    try { await api('/api/logout', { method: 'POST', body: JSON.stringify({}) }); } catch (_) {}
    loginPanel.hidden = false;
    dashboard.hidden = true;
    notify('تم تسجيل الخروج');
  });

  document.getElementById('refreshButton').addEventListener('click', loadMessages);
  filter.addEventListener('change', renderMessages);

  async function loadMessages() {
    try {
      const data = await api('/api/messages');
      allMessages = data.messages || [];
      totalCount.textContent = data.total ?? allMessages.length;
      unreadCount.textContent = data.unread ?? allMessages.filter((m) => !m.is_read).length;
      renderMessages();
    } catch (error) {
      if (error.status === 401) {
        loginPanel.hidden = false;
        dashboard.hidden = true;
      } else notify(error.message || 'تعذّر تحميل الرسائل.');
    }
  }

  function formatDate(iso) {
    if (!iso) return 'وقت غير متوفر';
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return 'وقت غير متوفر';
    return new Intl.DateTimeFormat('ar', { dateStyle: 'medium', timeStyle: 'short' }).format(date);
  }

  function renderMessages() {
    const visible = filter.value === 'unread' ? allMessages.filter((message) => !message.is_read) : allMessages;
    messageList.replaceChildren();
    emptyState.hidden = visible.length !== 0;
    messageList.hidden = visible.length === 0;
    visible.forEach((message) => {
      const article = document.createElement('article');
      article.className = `message-card${message.is_read ? '' : ' unread'}`;
      const head = document.createElement('div'); head.className = 'message-card-head';
      const mood = document.createElement('span'); mood.className = 'mood-tag'; mood.textContent = `♡ ${escapeText(message.mood || 'رسالة من القلب')}`;
      const date = document.createElement('time'); date.className = 'message-date'; date.dateTime = message.created_at || ''; date.textContent = formatDate(message.created_at);
      head.append(mood, date);
      const body = document.createElement('p'); body.className = 'message-body'; body.textContent = message.body;
      const footer = document.createElement('div'); footer.className = 'message-card-footer';
      const read = document.createElement('span'); read.className = 'read-status'; read.textContent = message.is_read ? '✓ تمت القراءة' : '● جديدة';
      const actions = document.createElement('div'); actions.className = 'card-actions';
      if (!message.is_read) {
        const markButton = document.createElement('button'); markButton.type = 'button'; markButton.textContent = 'تحديد كمقروءة';
        markButton.addEventListener('click', async () => {
          try { await api(`/api/messages/${message.id}/read`, { method: 'PATCH' }); await loadMessages(); notify('تم تحديد الرسالة كمقروءة'); }
          catch (error) { notify(error.message); }
        });
        actions.append(markButton);
      }
      const deleteButton = document.createElement('button'); deleteButton.type = 'button'; deleteButton.className = 'delete-button'; deleteButton.textContent = 'حذف';
      deleteButton.addEventListener('click', async () => {
        if (!window.confirm('هل أنت متأكدة من حذف هذه الرسالة نهائيًا؟')) return;
        try { await api(`/api/messages/${message.id}`, { method: 'DELETE' }); await loadMessages(); notify('تم حذف الرسالة'); }
        catch (error) { notify(error.message); }
      });
      actions.append(deleteButton); footer.append(read, actions); article.append(head, body, footer); messageList.append(article);
    });
  }

  document.getElementById('exportButton').addEventListener('click', () => {
    if (!allMessages.length) return notify('لا توجد رسائل لتصديرها الآن.');
    const quote = (value) => `"${String(value ?? '').replaceAll('"', '""')}"`;
    const rows = [['رقم الرسالة', 'نوع الرسالة', 'النص', 'التاريخ', 'مقروءة'], ...allMessages.map((m) => [m.id, m.mood, m.body, formatDate(m.created_at), m.is_read ? 'نعم' : 'لا'])];
    const csv = '\uFEFF' + rows.map((row) => row.map(quote).join(',')).join('\r\n');
    const link = document.createElement('a');
    link.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8;' }));
    link.download = `raghad-messages-${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.append(link); link.click(); link.remove(); URL.revokeObjectURL(link.href);
    notify('تم تجهيز ملف الرسائل للتنزيل');
  });

  checkSession();
})();
