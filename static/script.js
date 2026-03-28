// ── Admin Toggle ──
function toggleAdmin() {
    document.body.classList.toggle('admin-mode', document.getElementById('adminToggle').checked);
}

// ── Helpers ──
function getEmail() {
    var email = document.getElementById('globalEmail').value.trim();
    if (!email) {
        toast('Enter your email in the top bar first', 'error');
        document.getElementById('globalEmail').focus();
        return null;
    }
    return email;
}

function escapeHtml(text) {
    var d = document.createElement('div');
    d.textContent = text;
    return d.innerHTML;
}

// ── Toast ──
function toast(msg, type) {
    var c = document.getElementById('toastContainer');
    var el = document.createElement('div');
    el.className = 'toast ' + (type || 'info');
    el.textContent = msg;
    c.appendChild(el);
    setTimeout(function () {
        el.classList.add('removing');
        setTimeout(function () { el.remove(); }, 200);
    }, 3000);
}

// ── Response ──
function syntaxHighlight(json) {
    json = json.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    return json.replace(
        /("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g,
        function (match) {
            var cls = 'json-number';
            if (/^"/.test(match)) {
                if (/:$/.test(match)) {
                    cls = 'json-key';
                } else {
                    cls = 'json-string';
                }
            } else if (/true|false/.test(match)) {
                cls = 'json-bool';
            } else if (/null/.test(match)) {
                cls = 'json-null';
            }
            return '<span class="' + cls + '">' + match + '</span>';
        }
    );
}

function showResult(data) {
    var raw = JSON.stringify(data, null, 2);
    document.getElementById('result').innerHTML = syntaxHighlight(raw);
    var pill = document.getElementById('statusPill');
    if (data.result === 'ok') {
        pill.textContent = 'OK';
        pill.className = 'status-pill ok';
    } else if (data.result === 'nok') {
        pill.textContent = 'NOK';
        pill.className = 'status-pill nok';
    } else {
        pill.textContent = 'DATA';
        pill.className = 'status-pill data';
    }
}

// ── API ──
async function apiPost(url, body) {
    try {
        var res = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        var data = await res.json();
        showResult(data);
        return data;
    } catch (e) {
        toast('Connection error: ' + e.message, 'error');
        return null;
    }
}

async function apiGet(url) {
    try {
        var res = await fetch(url);
        var data = await res.json();
        showResult(data);
        return data;
    } catch (e) {
        toast('Connection error: ' + e.message, 'error');
        return null;
    }
}

// ── 1. Setup ──
async function seedData() {
    var data = await apiPost('/api/seed', {});
    if (data && data.result === 'ok') {
        toast('Test events created', 'success');
        getEvents();
    }
}

async function getEvents() {
    var data = await apiGet('/api/get-events');
    if (!data || !data.events) return;
    toast(data.events.length + ' active event(s)', 'success');

    var list = document.getElementById('eventsList');
    if (data.events.length === 0) {
        list.innerHTML = '<div style="padding:10px;color:#aaa;font-size:12px;">No active events</div>';
        return;
    }

    list.innerHTML = data.events.map(function (ev) {
        var pub = !ev.audience;
        var t1 = new Date(ev.start_time * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        var t2 = new Date(ev.end_time * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        return (
            '<div class="ev-row">' +
                '<span class="ev-title">' + escapeHtml(ev.title) + '</span>' +
                '<div class="ev-info">' +
                    '<span class="ev-badge ' + (pub ? 'pub' : 'priv') + '">' + (pub ? 'Public' : 'Private') + '</span>' +
                    '<span>' + t1 + '-' + t2 + '</span>' +
                    '<span>' + ev.participant_count + ' in</span>' +
                    '<span class="ev-id">' + escapeHtml(ev.event_id) + '</span>' +
                '</div>' +
            '</div>'
        );
    }).join('');
}

// ── 2. Start / Stop ──
async function startEvent() {
    var id = document.getElementById('ssEventId').value.trim();
    if (!id) return toast('Enter an event ID', 'error');
    var data = await apiPost('/api/start-event', { event_id: id });
    if (data && data.result === 'ok') toast('Event started', 'success');
    else if (data && data.result === 'nok') toast(data.reason, 'error');
}

async function stopEvent() {
    var id = document.getElementById('ssEventId').value.trim();
    if (!id) return toast('Enter an event ID', 'error');
    var data = await apiPost('/api/stop-event', { event_id: id });
    if (data && data.result === 'ok') toast('Event stopped', 'success');
    else if (data && data.result === 'nok') toast(data.reason, 'error');
}

// ── 3. Check-in / Check-out ──
async function doCheckin() {
    var email = getEmail(); if (!email) return;
    var id = document.getElementById('ccEventId').value.trim();
    if (!id) return toast('Enter an event ID', 'error');
    var data = await apiPost('/api/checkin', { email: email, event_id: id });
    if (data && data.result === 'ok') toast('Checked in successfully', 'success');
    else if (data && data.result === 'nok') toast(data.reason, 'error');
}

async function doCheckout() {
    var email = getEmail(); if (!email) return;
    var id = document.getElementById('ccEventId').value.trim();
    if (!id) return toast('Enter an event ID', 'error');
    var data = await apiPost('/api/checkout', { email: email, event_id: id });
    if (data && data.result === 'ok') toast('Checked out successfully', 'success');
    else if (data && data.result === 'nok') toast(data.reason, 'error');
}

async function doCheckinAdmin() {
    var email = getEmail(); if (!email) return;
    var id = document.getElementById('ccEventId').value.trim();
    if (!id) return toast('Enter an event ID', 'error');
    var data = await apiPost('/api/checkin-byadmin', { email: email, event_id: id });
    if (data && data.result === 'ok') toast('User checked in by admin', 'success');
    else if (data && data.result === 'nok') toast(data.reason, 'error');
}

async function doCheckoutAdmin() {
    var email = getEmail(); if (!email) return;
    var id = document.getElementById('ccEventId').value.trim();
    if (!id) return toast('Enter an event ID', 'error');
    var data = await apiPost('/api/checkout-byadmin', { email: email, event_id: id });
    if (data && data.result === 'ok') toast('User removed by admin', 'success');
    else if (data && data.result === 'nok') toast(data.reason, 'error');
}

// ── 4. Find Events ──
async function findEvents() {
    var email = getEmail(); if (!email) return;
    var x = document.getElementById('feLat').value;
    var y = document.getElementById('feLon').value;
    var data = await apiGet('/api/find-events?email=' + encodeURIComponent(email) + '&x=' + x + '&y=' + y);
    if (data && data.event_ids) toast('Found ' + data.event_ids.length + ' event(s) nearby', 'success');
}

// ── 5. Participants ──
async function getParticipants() {
    var id = document.getElementById('partEventId').value.trim();
    if (!id) return toast('Enter an event ID', 'error');
    var data = await apiGet('/api/get-participants?event_id=' + encodeURIComponent(id));
    if (data && data.participants) toast(data.participants.length + ' participant(s) found', 'success');
    else if (data && data.result === 'nok') toast(data.reason, 'error');
}

async function numParticipants() {
    var id = document.getElementById('partEventId').value.trim();
    if (!id) return toast('Enter an event ID', 'error');
    var data = await apiGet('/api/num-participants?event_id=' + encodeURIComponent(id));
    if (data && data.count !== undefined) toast(data.count + ' participant(s)', 'success');
    else if (data && data.result === 'nok') toast(data.reason, 'error');
}

// ── 6. Chat ──
async function postToChat() {
    var email = getEmail(); if (!email) return;
    var id = document.getElementById('chatEventId').value.trim();
    var text = document.getElementById('chatText').value.trim();
    if (!id) return toast('Enter an event ID', 'error');
    if (!text) return toast('Enter a message', 'error');
    var data = await apiPost('/api/post-to-chat', { email: email, event_id: id, text: text });
    if (data && data.result === 'ok') toast('Message sent', 'success');
    else if (data && data.result === 'nok') toast(data.reason, 'error');
}

async function getPosts() {
    var id = document.getElementById('chatEventId').value.trim();
    if (!id) return toast('Enter an event ID', 'error');
    var data = await apiGet('/api/get-posts?event_id=' + encodeURIComponent(id));
    if (data && data.posts) toast(data.posts.length + ' message(s) found', 'success');
    else if (data && data.result === 'nok') toast(data.reason, 'error');
}

async function getUserPosts() {
    var email = getEmail(); if (!email) return;
    var data = await apiGet('/api/get-user-posts?email=' + encodeURIComponent(email));
    if (data && data.posts) toast(data.posts.length + ' message(s) found', 'success');
}

// ── Init ──
document.addEventListener('DOMContentLoaded', getEvents);
