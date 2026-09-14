import { useEffect, useRef, useState } from 'react'
import { api } from './api.js'
import { STR } from './i18n.js'
import {
  connectQueue, getLang, getTicket, getCachedStatus, refreshStatusOfflineAware,
  saveTicket, setLang,
} from './state.js'

const CROPS = ['Paddy', 'Wheat', 'Maize']
const SIMPLE_KEY = 'mm_simple'
const isSimple = () => localStorage.getItem(SIMPLE_KEY) === '1'
const LANGS = [['ml', 'മലയാളം'], ['en', 'English'], ['hi', 'हिंदी'], ['ta', 'தமிழ்']]
const TTS_LANG = { ml: 'ml-IN', en: 'en-IN', hi: 'hi-IN', ta: 'ta-IN' }

function speak(text, lang) {
  try {
    const u = new SpeechSynthesisUtterance(text)
    u.lang = TTS_LANG[lang] || 'ml-IN'
    speechSynthesis.cancel()
    speechSynthesis.speak(u)
  } catch { /* TTS unsupported */ }
}

function Card({ children, className = '' }) {
  return <div className={`card ${className}`}>{children}</div>
}

function Stat({ label, value, sub, tone }) {
  return (
    <div className={`stat ${tone || ''}`}>
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}{sub ? ` · ${sub}` : ''}</div>
    </div>
  )
}

// ------------------------------ Farmer PWA --------------------------------- //

function FarmerView({ lang }) {
  const t = STR[lang]
  const [mandis, setMandis] = useState([])
  const [mandiId, setMandiId] = useState('KL-KOCHI-01')
  const [crop, setCrop] = useState('Paddy')
  const [qty, setQty] = useState(500)
  const [name, setName] = useState('')
  const [phone, setPhone] = useState('')
  const [slots, setSlots] = useState(null)
  const [chosen, setChosen] = useState(null)
  const [ticket, setTicket] = useState(getTicket())
  const [status, setStatus] = useState(null)
  const [offline, setOffline] = useState(false)
  const [error, setError] = useState('')
  const [priority, setPriority] = useState('')
  const [vehicle, setVehicle] = useState('')
  const [disputeMsg, setDisputeMsg] = useState('')
  const [passport, setPassport] = useState(null)
  const [explain, setExplain] = useState(null)
  const [voiceText, setVoiceText] = useState('')
  const [voiceProposal, setVoiceProposal] = useState(null)
  const [copilotText, setCopilotText] = useState('')
  const [copilotPlan, setCopilotPlan] = useState(null)
  const [dep, setDep] = useState(null)
  const [off, setOff] = useState(null)
  const [simple, setSimple] = useState(isSimple())
  const [notifCount, setNotifCount] = useState(0)
  const [bfm, setBfm] = useState(null)
  const [assistOpen, setAssistOpen] = useState(false)
  const [chat, setChat] = useState([{ role: 'bot', text: 'Namaskaram! Ask me: "When is my turn?", "What documents do I need?", "Where is the least crowded centre?"' }])
  const [chatQ, setChatQ] = useState('')
  const wsRef = useRef(null)

  useEffect(() => {
    api.get('/farmer/mandis').then((d) => setMandis(d.mandis)).catch(() => {})
  }, [])

  useEffect(() => {
    api.get(`/farmer/best-for-me?crop=${crop}&quantity_kg=${qty}`).then(setBfm).catch(() => {})
  }, [crop, qty])

  useEffect(() => {
    if (!mandiId) return
    api.get(`/farmer/slots?mandi_id=${mandiId}&quantity_kg=${qty}`).then((d) => {
      setSlots(d)
      setChosen(d.options?.[0] || null)
    }).catch(() => {})
  }, [mandiId, qty])

  const loadStatus = async (tk = ticket) => {
    if (!tk) return
    const { status: s, offline: off } = await refreshStatusOfflineAware(tk)
    setStatus(s)
    setOffline(off)
    api.get(`/farmer/passport?phone=${tk.phone}`).then(setPassport).catch(() => {})
    api.get(`/farmer/explain-payment?token=${tk.token}`).then(setExplain).catch(() => {})
    api.post('/farmer/copilot/departure', { token: tk.token }).then(setDep).catch(() => setDep(null))
    api.post('/farmer/copilot/transfer', { token: tk.token }).then(setOff).catch(() => setOff(null))
  }

  const askCopilot = async (text) => {
    if (!text.trim()) return
    try {
      const r = await api.post('/farmer/copilot/plan', {
        text, lang, lat: 10.52, lng: 76.21, // demo location; PWA uses GPS in deployment
      })
      setCopilotPlan(r)
      speak(r.reply || '', lang)
    } catch { /* keep silent */ }
  }

  const micListen = () => {
    try {
      const SR = window.SpeechRecognition || window.webkitSpeechRecognition
      const rec = new SR()
      rec.lang = TTS_LANG[lang] || 'ml-IN'
      rec.onresult = (e) => {
        const said = e.results[0][0].transcript
        setCopilotText(said)
        askCopilot(said)
      }
      rec.start()
    } catch { /* unsupported browser */ }
  }

  const bookPlan = async () => {
    if (!copilotPlan?.plan || phone.length !== 10) { setError('Enter your 10-digit mobile number first'); return }
    try {
      const b = await api.post('/farmer/book', {
        mandi_id: copilotPlan.plan.mandi_id, phone, farmer_name: name || 'Farmer',
        crop: copilotPlan.parse.crop || crop, quantity_kg: copilotPlan.parse.quantity_kg || Number(qty) || 500,
        slot_time: copilotPlan.plan.arrival_at?.slice(11, 16) || '14:00', lang,
      })
      saveTicket(b.token, b.phone); setTicket({ token: b.token, phone: b.phone })
      setCopilotPlan(null)
      await loadStatus({ token: b.token, phone: b.phone })
    } catch (e) { setError(e.message) }
  }

  const moveMe = async () => {
    try {
      const r = await api.post('/farmer/copilot/transfer', {
        token: status.token, to_mandi_id: off.recommended.mandi_id, confirm: true,
      })
      saveTicket(r.new_token, status.phone); setTicket({ token: r.new_token, phone: status.phone })
      setOff(null); await loadStatus({ token: r.new_token, phone: status.phone })
    } catch (e) { setError(e.message) }
  }

  useEffect(() => { loadStatus() /* eslint-disable-line */ }, [ticket?.token])

  // Live queue updates via WebSocket.
  useEffect(() => {
    if (!status?.mandi_id) return
    wsRef.current?.close()
    wsRef.current = connectQueue(status.mandi_id, (evt) => {
      if (evt.type === 'queue_update') loadStatus() /* eslint-disable-line */
    })
    return () => wsRef.current?.close()
  }, [status?.mandi_id]) // eslint-disable-line

  // Gentle polling fallback (also powers offline banner).
  useEffect(() => {
    const iv = setInterval(() => { if (ticket) loadStatus() }, 15000)
    return () => clearInterval(iv)
  }, [ticket]) // eslint-disable-line

  const book = async () => {
    setError('')
    try {
      const b = await api.post('/farmer/book', {
        mandi_id: mandiId, phone, farmer_name: name || 'Farmer',
        crop, quantity_kg: Number(qty), slot_time: chosen.slot_time, lang,
        priority_flag: priority || null,
        vehicle_type: vehicle || null,
      })
      const tk = { token: b.token, phone: b.phone }
      saveTicket(tk.token, tk.phone)
      setTicket(tk)
      await loadStatus(tk)
    } catch (e) { setError(e.message) }
  }


  const voiceBook = async (confirm = false) => {
    try {
      const r = await api.post('/farmer/voice-book', {
        phone: phone || '9000000000', farmer_name: name || 'Farmer', crop,
        quantity_kg: Number(qty) || 500,
        when: /tomorrow/i.test(voiceText) ? 'tomorrow' : 'nearest',
        confirm,
      })
      setVoiceProposal(r)
      speak(r.message || '', lang)
      if (confirm && r.token) {
        saveTicket(r.token, r.phone)
        setTicket({ token: r.token, phone: r.phone })
        setVoiceProposal(null); setVoiceText('')
        await loadStatus({ token: r.token, phone: r.phone })
      }
    } catch (e) { setError(e.message) }
  }

  const selfCheckIn = async () => {
    setError('')
    try {
      const m = mandis.find((x) => x.id === status.mandi_id)
      const r = await api.post('/farmer/self-checkin', {
        token: status.token, lat: m?.lat ?? 9.9312, lng: m?.lng ?? 76.2673,
      })
      alert(`${lang === 'ml' ? 'ചെക്ക് ഇൻ ആയി' : 'Checked in!'} Position ${r.position}, ETA ${r.eta_minutes} min`)
      await loadStatus()
    } catch (e) { setError(e.message) }
  }

  const notifications = async () => {
    if (!ticket) return
    const d = await api.get(`/farmer/notifications?phone=${ticket.phone}`)
    alert(d.notifications.map((n) => `[${n.channel}] ${n.body}`).join('\n') || 'No messages yet')
  }
  useEffect(() => { if (status) setNotifCount((c) => c + 1) }, [status?.status]) // eslint-disable-line

  const ask = async (question) => {
    if (!question.trim()) return
    setChat((c) => [...c, { role: 'you', text: question }])
    setChatQ('')
    try {
      const r = await api.post('/farmer/assistant', {
        question, token: ticket?.token, phone: ticket?.phone || phone,
        role: 'farmer', crop,
      })
      setChat((c) => [...c, { role: 'bot', text: r.reply }])
      speak(r.reply, lang)
    } catch { setChat((c) => [...c, { role: 'bot', text: 'Connection issue — try again.' }]) }
  }

  if (ticket && status) {
    const pos = status.position ?? '—'
    const eta = status.eta_minutes ?? '—'
    const isServing = status.queue_group === 'SERVING' || ['WEIGHING', 'QUALITY_CHECK', 'PAYMENT'].includes(status.status)
    const leaveNow = status.leave_home_alerted && status.status === 'SLOT_BOOKED'
    const turnSoon = status.turn_soon_alerted && status.status === 'ARRIVED'
    return (
      <div className="fade-in">
        {offline && <div className="banner warn">📴 {t.offline}</div>}
        {status.eta_delta != null && Math.abs(status.eta_delta) >= 1 && (
          <div className={`banner ${status.eta_delta > 0 ? 'ok-banner' : 'warn'}`}>
            {status.eta_delta > 0
              ? `⚡ Queue re-optimized: your wait just dropped ${status.eta_delta} min`
              : `⏳ Queue updated: wait increased by ${Math.abs(status.eta_delta)} min`}
          </div>
        )}
        {leaveNow && <div className="banner alert">🚗 {t.leaveNow} — {t.token} {status.token}</div>}
        {dep?.advice && dep.advice !== 'come' && (
          <div className={`banner ${dep.advice === 'wait' ? 'warn' : 'ok-banner'}`}>
            {dep.advice === 'wait' ? '🟡 ' : '🟢 '}<b>{dep.message}</b>
          </div>
        )}
        {off?.offer && (
          <div className="banner warn">
            ⚖ Your current wait is ~{off.current_wait_minutes}m — <b>{off.recommended.name}</b> could save you
            ~{Math.round(off.recommended.wait_advantage_minutes)}m (+{off.recommended.distance_km} km).
            <button className="mini" onClick={moveMe}>Move me there</button>
            <button className="mini ghost" onClick={() => setOff({ ...off, offer: false })}>Stay here</button>
          </div>
        )}
        {turnSoon && <div className="banner alert">🔔 {t.turnSoon}</div>}
        <Card className="hero">
          <div className="token-row">
            <div>
              <div className="token-label">{t.token}</div>
              <div className="token">{status.token}</div>
              <div className="muted">{status.mandi_name}</div>
            </div>
            <div className="stage-badge">{status.status.replace('_', ' ')}</div>
          </div>
          <div className="grid3">
            <Stat label={t.position} value={isServing ? 'Now' : pos} />
            <Stat label={t.eta} value={eta === '—' ? '—' : `${eta} min`}
                  sub={status.eta_delta != null && status.eta_delta !== 0 ?
                    (status.eta_delta > 0 ? `⬇ ${status.eta_delta}m faster` : `⬆ ${Math.abs(status.eta_delta)}m slower`) : undefined} />
            <Stat label={t.confidence} value={status.eta_confidence ? `${Math.round(status.eta_confidence * 100)}%` : '—'} />
          </div>
          <button className="ghost" style={{ marginBottom: 8 }}
                  onClick={() => { const v = !simple; setSimple(v); localStorage.setItem(SIMPLE_KEY, v ? '1' : '0') }}>
            {simple ? '📖 Detailed mode' : '🟢 Simple mode'}
          </button>
          {simple ? (
            <div className="simple-grid">
              <div className="simple-btn">📅 <span>MY TURN</span><b>{isServing ? 'NOW' : `#${pos} · ${eta === '—' ? '—' : eta + 'm'}`}</b></div>
              {dep?.advised_departure_hhmm && status.status === 'SLOT_BOOKED' &&
                <div className="simple-btn"><span>START AT</span><b>{dep.advised_departure_hhmm}</b></div>}
              <div className="simple-btn">💰 <span>PAYMENT</span><b>{status.payment_status || '—'}</b></div>
              <button className="simple-btn" onClick={() => speak(`Your token ${status.token}. Position ${pos}. Expected wait ${eta} minutes.`, lang)}>
                🔊 <span>LISTEN</span><b>▶</b>
              </button>
            </div>
          ) : (
          <div className="qr-row">
            <img src={`/api/farmer/qrcode/${status.token}`} alt="Gate QR" className="qr-img" />
            <div>
              <b>Gate pass QR</b>
              <p className="muted">Show at the entry gate — staff scan or match the code.</p>
              {status.leave_home_alerted && !status.alert_ack_at && status.status === 'SLOT_BOOKED' && (
                <button className="mini" onClick={async () => {
                  await api.post('/farmer/alerts/ack', { token: status.token })
                  await loadStatus()
                }}>✓ Acknowledge alert (stop reminders)</button>
              )}
            </div>
          </div>
          )}
          {status.amount ? (
            <div className="amount-box">
              <span>₹{status.amount.toLocaleString('en-IN')}</span>
              <span className="muted"> {t.payment}: {status.payment_status}</span>
              {status.payment_status === 'DELAYED' && <span className="warn-text"> ⚠ delay detected</span>}
            </div>
          ) : null}
          {status.status === 'SLOT_BOOKED' && (
            <button className="primary big" onClick={selfCheckIn}>📍 {lang === 'ml' ? 'എത്തി — ചെക്ക് ഇൻ ചെയ്യുക' : "I've arrived — check in (GPS)"}</button>
          )}
          {disputeMsg && <p className="ok-text">{disputeMsg}</p>}
        </Card>

        {['PAYMENT', 'COMPLETED'].includes(status.status) && <DisputeBox token={status.token} onDone={setDisputeMsg} />}

        <Card>
          <h3>🧾 My procurement passport</h3>
          {passport ? (
            <>
              <div className="grid3">
                <Stat label="Visits" value={passport.totals.visits} />
                <Stat label="Completed" value={passport.totals.completed} tone="ok" />
                <Stat label="Avg time at centre" value={`${passport.totals.avg_wait_minutes}m`} />
              </div>
              <p className="muted">Mandi Mitra ID {passport.farmer.mm_id} · payments received {passport.totals.payments_received}</p>
              {passport.by_crop.map((c) => (
                <div key={c.crop} className="muted">🌾 {c.crop}: {c.visits} visits · {c.completed} completed · ₹{(c.earned || 0).toLocaleString('en-IN')} earned</div>
              ))}
            </>
          ) : <p className="muted">History loads after your first visit.</p>}
        </Card>

        {explain && (
          <Card>
            <h3>💡 Explain my payment</h3>
            <div className="timeline">
              {explain.checklist.map((s) => (
                <div key={s.step} className={`tl-step ${s.done ? 'done' : ''}`}>
                  <div className="tl-dot">{s.done ? '✓' : '•'}</div>
                  <div>
                    <div className="tl-name">{s.step}</div>
                    {s.pending_detail && <div className="tl-ts">{s.pending_detail}</div>}
                  </div>
                </div>
              ))}
            </div>
            <p className="advice-line">{explain.summary}</p>
          </Card>
        )}

        <Card>
          <h3>🧭 {t.timeline}</h3>
          <Timeline events={status.timeline || []} />
        </Card>

        {status.status === 'COMPLETED' && <ReceiptBox token={status.token} t={t} />}

        <div className="row-btns">
          <button className="ghost" onClick={notifications}>💬 {t.notifications}</button>
          <button className="ghost" onClick={() => {
            const pos = isServing ? 'now' : `position ${pos}`
            speak(`Your token ${status.token}. ${pos}. Expected wait ${eta} minutes.`, lang)
          }}>🔊 Listen (voice)</button>
          <button className="ghost" onClick={async () => {
            const r = await api.post('/farmer/ivr/call', { phone: status.phone, token: status.token, lang })
            speak(r.ivr_says, lang)
          }}>📞 Simulate IVR call</button>
          <button className="ghost" onClick={() => { localStorage.removeItem('mm_ticket'); setTicket(null); setStatus(null) }}>↺ New booking</button>
        </div>
        <p className="muted center">{t.bookBySms}</p>
        {notifCount < 0 && <span />}
        <AssistantChat open={assistOpen} setOpen={setAssistOpen} chat={chat} chatQ={chatQ} setChatQ={setChatQ} ask={ask} />
      </div>
    )
  }

  return (
    <div className="fade-in">
      <button className="ghost assist-fab" onClick={() => setAssistOpen(!assistOpen)}>🤖 Ask Mandi Mitra</button>
      <AssistantChat open={assistOpen} setOpen={setAssistOpen} chat={chat} chatQ={chatQ} setChatQ={setChatQ} ask={ask} />
      <Card className="hero copilot">
        <h3>🧠 {lang === 'ml' ? 'എവിടെയാണ് ഇന്ന് വേഗം?' : 'Where should I sell today?'}</h3>
        <div className="row-btns" style={{ marginBottom: 6 }}>
          {["I have 20 bags of paddy for today 3 pm", "എനിക്ക് ഇന്ന് 10 സഞ്ചി നെല്ല് വേണം", "Where is the queue shortest for 500 kg wheat?"].map((s) => (
            <button key={s} className="mini" onClick={() => { setCopilotText(s); askCopilot(s) }}>💬 {s.slice(0, 28)}…</button>
          ))}
          <button className="ghost" onClick={async () => {
            try {
              const b = await api.post('/farmer/demo/book', { lang })
              saveTicket(b.token, b.phone); setTicket({ token: b.token, phone: b.phone })
              await loadStatus({ token: b.token, phone: b.phone })
            } catch (e) { setError(e.message) }
          }}>🎬 1-tap demo booking</button>
        </div>
        <p className="muted">Just say it in your own words — the copilot does the rest.</p>
        <div className="grid2">
          <input value={copilotText} onChange={(e) => setCopilotText(e.target.value)}
                 onKeyDown={(e) => e.key === 'Enter' && askCopilot(copilotText)}
                 placeholder={lang === 'ml' ? '“ഇന്ന് 10 സഞ്ചി നെല്ല് കൊണ്ടുപോകണം”' : '"I have 20 bags of paddy for today 3 pm"'} />
          <div className="row-btns">
            <button className="primary" style={{ marginTop: 0 }} onClick={() => askCopilot(copilotText)}>Get my plan</button>
            <button className="ghost" onClick={micListen} title="Speak in your language">🎙</button>
          </div>
        </div>
        {copilotPlan && (
          <div className="advice">
            <p className="advice-line"><b>🤖 {copilotPlan.reply}</b></p>
            {copilotPlan.plan && (
              <>
                <div className="grid4">
                  <Stat label="Leave home" value={copilotPlan.plan.leave_at_hhmm} tone="ok" />
                  <Stat label="Queue ahead" value={copilotPlan.plan.queue_length} />
                  <Stat label="Expected wait" value={`${Math.round(copilotPlan.plan.expected_wait_minutes)}m`} />
                  {copilotPlan.plan.estimated_value && <Stat label="Est. value" value={`₹${copilotPlan.plan.estimated_value.toLocaleString('en-IN')}`} tone="ok" />}
                </div>
                <p className="muted" style={{ fontSize: '0.8rem' }}>📄 Carry: {copilotPlan.plan.documents}</p>
                {copilotPlan.assumptions.length > 0 && <p className="muted" style={{ fontSize: '0.75rem' }}>Note: {copilotPlan.assumptions.join(', ')}</p>}
                <div className="grid2">
                  <input value={phone} onChange={(e) => setPhone(e.target.value.replace(/\D/g, '').slice(0, 10))} placeholder="Mobile number to book" inputMode="numeric" />
                  <button className="primary" onClick={bookPlan} disabled={phone.length !== 10}>✅ Book this plan</button>
                </div>
              </>
            )}
            <p className="muted" style={{ fontSize: '0.75rem' }}>Plan confidence {Math.round((copilotPlan.confidence || 0) * 100)}%</p>
          </div>
        )}
      </Card>
      {bfm?.recommended && (
        <Card className="hero bfm">
          <h3>🏆 Best centre for you (AI)</h3>
          <div className="bfm-row">
            <div>
              <b>{bfm.recommended.name}</b> · {bfm.recommended.district}
              <div className="muted">
                {bfm.recommended.total_journey_minutes} min total · {bfm.recommended.queue_length} in queue ·
                {bfm.recommended.rate && ` ₹${bfm.recommended.rate.rate_per_quintal}/quintal`} ·
                ⭐ {bfm.recommended.rating.score ?? '—'}/5
              </div>
              {bfm.recommended.estimated_value && (
                <div className="ok-text">Est. value: ₹{bfm.recommended.estimated_value.toLocaleString('en-IN')}</div>
              )}
            </div>
            <button className="mini" onClick={() => { setMandiId(bfm.recommended.mandi_id); window.scrollTo({ top: 0, behavior: 'smooth' }) }}>
              Book here
            </button>
          </div>
          <div className="muted" style={{ fontSize: '0.75rem' }}>{bfm.why.join(' · ')}</div>
        </Card>
      )}
      <Card className="hero">
        <h2>🌾 {t.book}</h2>
        <label>{t.mandi}</label>
        <select value={mandiId} onChange={(e) => setMandiId(e.target.value)}>
          {mandis.map((m) => (
            <option key={m.id} value={m.id}>
              {m.status === 'OPEN' ? '🟢' : '⛔'} {m.name} · {m.congestion === 'HIGH' ? '🔴' : m.congestion === 'MODERATE' ? '🟡' : '🟢'} {m.queue_length} waiting
            </option>
          ))}
        </select>
        <div className="grid2">
          <div>
            <label>{t.crop}</label>
            <select value={crop} onChange={(e) => setCrop(e.target.value)}>
              {CROPS.map((c) => <option key={c}>{c}</option>)}
            </select>
          </div>
          <div>
            <label>{t.qty}</label>
            <input type="number" min="1" value={qty} onChange={(e) => setQty(e.target.value)} />
          </div>
        </div>
        <label>{t.name}</label>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Rajan Kumar" />
        <label>🚚 Vehicle / load (helps unloading prep)</label>
        <select value={vehicle} onChange={(e) => setVehicle(e.target.value)}>
          <option value="">— Not specified —</option>
          <option>Tractor</option>
          <option>Truck</option>
          <option>Mini truck</option>
          <option>Auto</option>
          <option>Other</option>
        </select>
        <label>📱 Mobile number</label>
        <input value={phone} onChange={(e) => setPhone(e.target.value.replace(/\D/g, '').slice(0, 10))}
               placeholder="9876500000" inputMode="numeric" />
        {!phone && <p className="muted">Booking confirmation and SMS/IVR alerts go to this number.</p>}
      </Card>

      {slots && (
        <Card>
          <h3>🤖 {t.slot} — AI recommendations</h3>
          <div className="slot-list">
            {slots.options.slice(0, 5).map((o) => (
              <button key={o.slot_time} className={`slot ${chosen?.slot_time === o.slot_time ? 'sel' : ''}`}
                      onClick={() => setChosen(o)}>
                <span className="slot-time">🕐 {o.slot_time}</span>
                <span className="muted">wait ~{o.expected_wait_min}m · {o.queue_ahead} ahead</span>
                {o.recommended && <span className="pill">★ {t.recommended} {Math.round(o.confidence * 100)}%</span>}
              </button>
            ))}
          </div>
          <label>♿ Priority request <span className="muted">(elderly / disabled / small holder get queue precedence)</span></label>
          <select value={priority} onChange={(e) => setPriority(e.target.value)}>
            <option value="">— None —</option>
            <option value="ELDERLY">Senior citizen (60+)</option>
            <option value="DISABLED">Differently-abled</option>
            <option value="SMALL_HOLDER">Small holder (&lt; 500 kg)</option>
          </select>
          <button className="primary big" onClick={book} disabled={!chosen || phone.length !== 10}>{t.confirmBooking}</button>
          {error && <p className="error">{error}</p>}
        </Card>
      )}

      <Card>
        <h3>🎙 Voice-to-action booking <span className="muted">(confirms before anything is booked)</span></h3>
        <div className="grid2">
          <input value={voiceText} onChange={(e) => setVoiceText(e.target.value)}
                 placeholder='"Book tomorrow morning at the nearest mandi"' />
          <button className="primary" style={{ marginTop: 0 }} onClick={() => voiceBook(false)}>🎙 Simulate voice request</button>
        </div>
        {voiceProposal && (
          <div className="advice">
            <p className="advice-line">🤖 {voiceProposal.message}</p>
            {voiceProposal.needs_confirmation && (
              <button className="primary" onClick={() => voiceBook(true)}>✅ Yes — confirm my booking</button>
            )}
            {voiceProposal.token && <p className="ok-text">Booked! Token {voiceProposal.token}</p>}
          </div>
        )}
      </Card>
    </div>
  )
}

const STAGE_ORDER = ['BOOKING_CREATED', 'ARRIVAL_VERIFIED', 'WEIGHING', 'QUALITY_CHECK', 'PROCUREMENT_APPROVED', 'PAYMENT_COMPLETED']

function Timeline({ events }) {
  const actions = events.map((e) => e.action)
  return (
    <div className="timeline">
      {STAGE_ORDER.map((stage) => {
        const evt = events.filter((e) => e.action === stage).slice(-1)[0]
        const done = actions.includes(stage)
        const isLast = actions.indexOf(stage) === actions.length - 1
        return (
          <div key={stage} className={`tl-step ${done ? 'done' : ''} ${done && isLast ? 'current' : ''}`}>
            <div className="tl-dot">{done ? '✓' : '•'}</div>
            <div>
              <div className="tl-name">{stage.replace(/_/g, ' ')}</div>
              {evt && <div className="tl-ts">{evt.ts.replace('T', ' ').slice(0, 16)} · {evt.actor}</div>}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function ReceiptBox({ token, t }) {
  const [rec, setRec] = useState(null)
  useEffect(() => {
    api.get(`/farmer/receipt/${token}`).then(setRec).catch(() => {})
  }, [token])
  if (!rec) return null
  const p = rec.receipt.payload
  return (
    <Card>
      <h3>🧾 {t.receipt}</h3>
      <div className="receipt">
        <div className="receipt-row"><span>Token</span><b>{p.token}</b></div>
        <div className="receipt-row"><span>Crop</span><span>{p.crop} · Grade {p.quality_grade}</span></div>
        <div className="receipt-row"><span>Quantity</span><span>{p.quantity_kg} kg</span></div>
        <div className="receipt-row"><span>Amount</span><b>₹{p.amount.toLocaleString('en-IN')}</b></div>
        <div className="receipt-hash">hash {rec.receipt.hash.slice(0, 24)}…</div>
      </div>
      {rec.chain_verified && <p className="ok-text">🔗 {t.chainVerified}</p>}
    </Card>
  )
}

function DisputeBox({ token, onDone }) {
  const [category, setCategory] = useState('WEIGHT')
  const [note, setNote] = useState('')
  const [done, setDone] = useState(false)

  const submit = async () => {
    try {
      await api.post('/farmer/dispute', { token, category, note })
      setDone(true)
      onDone?.('Dispute recorded — immutable timestamp logged for review.')
    } catch { /* ignore */ }
  }

  if (done) return <Card><p className="ok-text">✅ Dispute recorded — immutable timestamp logged. Track it in the journey timeline.</p></Card>
  return (
    <Card>
      <h3>⚖ Raise a concern (dispute)</h3>
      <p className="muted">Weight · quality · payment — every flag is timestamped and cannot be altered.</p>
      <div className="grid2">
        <div>
          <label>Category</label>
          <select value={category} onChange={(e) => setCategory(e.target.value)}>
            <option value="WEIGHT">Weight mismatch</option>
            <option value="QUALITY">Quality grade dispute</option>
            <option value="PAYMENT">Payment amount / delay</option>
            <option value="GENERAL">General</option>
          </select>
        </div>
        <div>
          <label>Note</label>
          <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Describe the issue" />
        </div>
      </div>
      <button className="primary" onClick={submit}>Submit dispute flag</button>
    </Card>
  )
}

// ------------------------------ Staff view --------------------------------- //

function StaffView({ lang, onLogout }) {
  const t = STR[lang]
  const [jwt, setJwt] = useState(sessionStorage.getItem('mm_jwt') || '')
  const [u, setU] = useState(sessionStorage.getItem('mm_user') || 'staff1')
  const [p, setP] = useState('')
  const [dash, setDash] = useState(null)
  const [queue, setQueue] = useState(null)
  const [bott, setBott] = useState(null)
  const [anom, setAnom] = useState(null)
  const [sla, setSla] = useState(null)
  const [whatif, setWhatif] = useState(null)
  const [disputes, setDisputes] = useState(null)
  const [walkin, setWalkin] = useState({ name: '', phone: '', crop: 'Paddy', qty: 500, priority: '' })
  const [agent, setAgent] = useState({ name: '', phone: '', slot: '14:00' })
  const [channels, setChannels] = useState([])
  const [briefing, setBriefing] = useState(null)
  const [twin, setTwin] = useState(null)
  const [heat, setHeat] = useState(null)
  const [twinScenario, setTwinScenario] = useState({ counters: '', multiplier: 1.0 })
  const [cap, setCap] = useState(null)
  const [mh, setMh] = useState(null)
  const [ins, setIns] = useState(null)
  const [trust, setTrust] = useState(null)
  const [slow, setSlow] = useState(null)
  const [emergency, setEmergency] = useState(false)
  const [err, setErr] = useState('')

  const load = async () => {
    try {
      const [d, q, b, a, s, w, dp, ch, br, ht, cp, mhd, insd, tsd, slw] = await Promise.all([
        api.get('/staff/dashboard', jwt),
        api.get('/staff/queue', jwt),
        api.get('/staff/bottleneck', jwt),
        api.get('/staff/anomalies', jwt),
        api.get('/staff/sla', jwt),
        api.get('/staff/whatif', jwt),
        api.get('/staff/disputes', jwt),
        api.get('/staff/notifications?limit=12', jwt),
        api.get('/staff/briefing', jwt),
        api.get('/staff/heatmap', jwt),
        api.get('/staff/capacity-plan', jwt),
        api.get('/staff/model-health', jwt),
        api.get('/staff/insider', jwt),
        api.get('/staff/trust-score', jwt),
        api.get('/staff/counter-slowdown', jwt),
      ])
      setDash(d); setQueue(q); setBott(b); setAnom(a); setSla(s); setWhatif(w); setDisputes(dp)
      setChannels(ch.notifications || []); setBriefing(br); setHeat(ht); setErr('')
      setCap(cp); setMh(mhd); setIns(insd); setTrust(tsd); setSlow(slw)
    } catch (e) { setErr(e.message) }
  }

  useEffect(() => {
    if (!jwt) return
    load() // eslint-disable-line
    const iv = setInterval(load, 8000)
    return () => clearInterval(iv)
  }, [jwt]) // eslint-disable-line

  const login = async () => {
    setErr('')
    try {
      const r = await api.post('/staff/login', { username: u, password: p })
      setJwt(r.access_token)
      sessionStorage.setItem('mm_jwt', r.access_token)
      sessionStorage.setItem('mm_user', u)
    } catch (e) { setErr(e.message) }
  }

  const act = async (path, body) => {
    try { await api.post(path, body, jwt); await load() } catch (e) { setErr(e.message) }
  }

  if (!jwt) {
    return (
      <Card className="hero narrow fade-in">
        <h2>🔐 {t.staffLogin}</h2>
        <label>{t.username}</label>
        <input value={u} onChange={(e) => setU(e.target.value)} />
        <label>{t.password}</label>
        <input type="password" value={p} onChange={(e) => setP(e.target.value)} placeholder="staff123" />
        <button className="primary big" onClick={login}>{t.staffLogin}</button>
        {err && <p className="error">{err}</p>}
        <p className="muted">demo: staff1/staff123 (mandi) · admin/admin123 (district)</p>
      </Card>
    )
  }

  const fc = dash?.congestion_forecast?.hours || []
  return (
    <div className="fade-in">
      <div className="row-btns spread">
        <h2>🖥 {t.dashboard} — {dash?.mandi_id}</h2>
        <div>
          <button className="ghost" onClick={() => act('/staff/autopilot', { steps: 4 })}>▶ {t.autopilot}</button>
          <button className="ghost" onClick={() => act('/staff/ivr-broadcast', { lang })}>📣 IVR broadcast</button>
          <button className="ghost" onClick={() => window.open('/api/staff/report/daily.csv', '_blank')}
                  style={{ display: 'none' }} />
          <a className="ghost" href="/api/staff/report/daily.csv" download>📄 Daily CSV</a>
          <button className="ghost" onClick={() => act('/staff/scenario/congestion', {})}>⚡ Congestion scenario</button>
          <button className="ghost" onClick={async () => {
            try {
              const r = await api.post('/staff/demo/full', {}, jwt)
              alert(`🎬 Demo loaded: ${r.actions} actions — autopilot moved the queue, ETAs updated live`)
              await load()
            } catch (e) { setErr(e.message) }
          }}>🎬 1-click demo</button>
          <button className="ghost" onClick={async () => {
            try {
              const r = await api.post('/staff/prevention-sweep', {}, jwt)
              alert(r.farmers_warned > 0
                ? `🛡 ${r.farmers_warned} at-home farmer(s) warned to stay back — queue prevented, not just monitored`
                : '🛡 No congestion right now — no warnings needed')
              await load()
            } catch (e) { setErr(e.message) }
          }}>🛡 Prevention sweep</button>
          <button className={`ghost ${emergency ? 'danger' : ''}`} onClick={async () => {
            const next = !emergency
            await act('/staff/emergency-mode', { active: next, reason: next ? 'emergency closure (drill)' : '' })
            setEmergency(next)
          }}>{emergency ? '🟢 End emergency' : '🚨 Emergency mode'}</button>
          <button className="ghost" onClick={async () => {
            try {
              const r = await api.get('/staff/daily-report', jwt)
              alert(`📋 MANDI DAILY REPORT — ${r.date}\nFarmers served: ${r.farmers_served}\nCompleted: ${r.completed} · No-shows: ${r.no_shows}\nAvg wait: ${r.avg_wait_minutes} min · Peak queue hour: ${r.peak_queue_hour}\nPayments pending: ${r.payments_pending} · Amount: ₹${Number(r.amount_procured_rs).toLocaleString('en-IN')}\nMain bottleneck: ${r.main_bottleneck || '—'}\nAI recommendation: ${r.ai_recommendation}`)
            } catch (e) { setErr(e.message) }
          }}>📋 Daily report</button>
          <button className="ghost" onClick={() => { sessionStorage.clear(); onLogout() }}>⎋</button>
        </div>
      </div>
      {err && <p className="error">{err}</p>}
      {briefing && (
        <div className="banner ok-banner">
          🧑‍✈️ <b>Staff Copilot:</b> {briefing.headline} {briefing.recommendation}
          {briefing.payments_needing_attention > 0 && ` · ${briefing.payments_needing_attention} payment case(s) need attention`}
          {briefing.sla_breaches_now > 0 && ` · ${briefing.sla_breaches_now} SLA breach(es) now`}
        </div>
      )}
      {emergency && (
        <div className="banner alert">
          🚨 EMERGENCY MODE ACTIVE — bookings frozen, centre marked CLOSED. Affected farmers notified and directed to alternative centres per procurement rules.
        </div>
      )}
      {sla?.breaches?.length > 0 && (
        <div className="banner alert">
          ⏱ SLA breach: {sla.breaches.map((b) => `${b.token} (${b.waited_minutes}m)`).join(', ')} waiting over {sla.threshold_minutes} min — serve or call now.
        </div>
      )}
      {dash && (
        <div className="grid4">
          <Stat label={t.queue} value={dash.queue_length} tone="warn" />
          <Stat label="Avg wait" value={`${dash.avg_wait_minutes}m`} />
          <Stat label="Processed" value={dash.processed_today} tone="ok" />
          <Stat label="No-shows" value={dash.no_shows} />
          <Stat label="Payments pending" value={dash.payments_pending} tone={dash.payments_pending ? 'warn' : ''} />
          <Stat label="Delayed" value={dash.payments_delayed} tone={dash.payments_delayed ? 'bad' : ''} />
          <Stat label="Procured today" value={`₹${(dash.amount_today / 1000).toFixed(1)}k`} tone="ok" />
          <Stat label="Anomaly flags" value={dash.anomaly_flags} tone={dash.anomaly_flags ? 'bad' : ''} />
        </div>
      )}

      {fc.length > 0 && (
        <Card>
          <h3>📈 {t.forecast}</h3>
          <div className="forecast">
            {fc.map((h) => (
              <div key={h.hour} className="fc-col">
                <div className={`fc-bar ${h.level.toLowerCase()}`} style={{ height: 8 + h.expected_arrivals * 4 }} />
                <span>{h.label.slice(0, 2)}</span>
                <span className={`fc-dot ${h.level.toLowerCase()}`} />
              </div>
            ))}
          </div>
        </Card>
      )}

      <div className="grid2">
        <Card>
          <h3>🚦 {t.counters}</h3>
          {dash?.counters.map((c) => (
            <div key={c.id} className="counter-row">
              <span className={`counter ${c.is_active ? (c.ticket_token ? 'busy' : 'idle') : 'off'}`}>
                {c.code} · {c.type === 'WEIGHING' ? '⚖' : '🔍'} {c.ticket_token || (c.is_active ? 'free' : 'offline')}
              </span>
              <button className="mini" onClick={() => act('/staff/counter', { counter_id: c.id, is_active: !c.is_active })}>
                {c.is_active ? 'Take offline' : 'Bring online'}
              </button>
            </div>
          ))}
          {(slow?.counters || []).filter((c) => c.flag).map((c, i) => (
            <div key={i} className="anomaly sev-high" style={{ marginTop: 8 }}>⚠ {c.flag}</div>
          ))}
          {bott && (
            <div className="advice">
              <h4>🤖 {t.bottleneck}</h4>
              {bott.recommendations.length === 0 && <p className="muted">All good — no action needed.</p>}
              {bott.recommendations.map((r, i) => <p key={i} className="advice-line">→ {r}</p>)}
              {whatif && (
                <div className="whatif">
                  <h4>🧮 What-if (projected wait)</h4>
                  <p className="advice-line">Now: <b>{whatif.current_wait_minutes}m</b> with {whatif.active_counters} counters</p>
                  {whatif.scenarios.map((s) => (
                    <p key={s.scenario} className="advice-line">
                      {s.scenario}: <b>{s.projected_wait_minutes}m</b> ({s.delta_minutes > 0 ? '+' : ''}{s.delta_minutes}m)
                    </p>
                  ))}
                </div>
              )}
            </div>
          )}
        </Card>
        <Card>
          <h3>🚨 {t.anomalies} ({anom?.flag_count ?? 0})</h3>
          {anom?.flags.length === 0 && <p className="muted">No anomalies detected.</p>}
          {anom?.flags.map((f, i) => (
            <div key={i} className={`anomaly sev-${f.severity.toLowerCase()}`}>
              <b>{f.type}</b> — {f.detail}
              <div className="muted">{f.recommendation}</div>
            </div>
          ))}
        </Card>
      </div>

      <Card>
        <h3>🚶 Walk-in / kiosk token</h3>
        <div className="grid4">
          <div><label>Name</label><input value={walkin.name} onChange={(e) => setWalkin({ ...walkin, name: e.target.value })} placeholder="Farmer name" /></div>
          <div><label>Phone</label><input value={walkin.phone} onChange={(e) => setWalkin({ ...walkin, phone: e.target.value.replace(/\D/g, '').slice(0, 10) })} placeholder="10 digits" /></div>
          <div><label>Crop</label>
            <select value={walkin.crop} onChange={(e) => setWalkin({ ...walkin, crop: e.target.value })}>
              {CROPS.map((c) => <option key={c}>{c}</option>)}
            </select>
          </div>
          <div><label>Qty (kg)</label><input type="number" value={walkin.qty} onChange={(e) => setWalkin({ ...walkin, qty: e.target.value })} /></div>
        </div>
        <div className="grid2">
          <div><label>Priority</label>
            <select value={walkin.priority} onChange={(e) => setWalkin({ ...walkin, priority: e.target.value })}>
              <option value="">— None —</option>
              <option value="ELDERLY">Senior citizen</option>
              <option value="DISABLED">Differently-abled</option>
              <option value="SMALL_HOLDER">Small holder</option>
            </select>
          </div>
          <div style={{ display: 'flex', alignItems: 'flex-end' }}>
            <button className="primary" style={{ marginTop: 0 }}
                    disabled={walkin.phone.length !== 10 || !walkin.name}
                    onClick={async () => {
                      try {
                        const r = await api.post('/staff/walkin', {
                          farmer_name: walkin.name, phone: walkin.phone, crop: walkin.crop,
                          quantity_kg: Number(walkin.qty), priority_flag: walkin.priority || null,
                        })
                        alert(`Token ${r.token} issued — position ${r.position}, ETA ${r.eta_minutes ?? '—'} min`)
                        setWalkin({ name: '', phone: '', crop: 'Paddy', qty: 500, priority: '' })
                        await load()
                      } catch (e) { setErr(e.message) }
                    }}>Issue token</button>
          </div>
        </div>
      </Card>

      {disputes?.count > 0 && (
        <Card>
          <h3>⚖ Open disputes ({disputes.count})</h3>
          {disputes.open_disputes.map((d, i) => (
            <div key={i} className="anomaly sev-high">
              <b>{d.token}</b> — {(() => { try { const j = JSON.parse(d.details); return `${j.category}: ${j.note}` } catch { return d.details } })()}
              <div className="muted">raised {d.raised_at} · ticket status {d.status}</div>
            </div>
          ))}
        </Card>
      )}

      <Card>
        <h3>🔮 Digital Twin — simulate before deciding</h3>
        <div className="grid4">
          <div><label>Counters</label>
            <select value={twinScenario.counters} onChange={(e) => setTwinScenario({ ...twinScenario, counters: e.target.value })}>
              <option value="">live</option>
              {[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </div>
          <div><label>Arrival surge</label>
            <select value={twinScenario.multiplier} onChange={(e) => setTwinScenario({ ...twinScenario, multiplier: Number(e.target.value) })}>
              <option value={0.7}>−30%</option>
              <option value={1}>normal</option>
              <option value={1.5}>+50%</option>
              <option value={2}>×2</option>
            </select>
          </div>
          <div style={{ display: 'flex', alignItems: 'flex-end' }}>
            <button className="primary" style={{ marginTop: 0 }} onClick={async () => {
              const qs = new URLSearchParams()
              if (twinScenario.counters) qs.set('counters', twinScenario.counters)
              qs.set('multiplier', twinScenario.multiplier)
              setTwin(await api.get(`/staff/twin?${qs}`, jwt))
            }}>Run simulation</button>
          </div>
          <div style={{ alignSelf: 'flex-end' }}>
            {twin && <div className="advice">
              <div>Now: <b>{twin.eta_now_minutes}m</b> wait · {twin.current_queue} in queue</div>
              <div>End-of-day queue: <b>{twin.projected_end_queue}</b></div>
              <div>Peak queue: <b>{twin.peak_queue}</b></div>
            </div>}
          </div>
        </div>
        {heat && (
          <div className="heat-row">
            {heat.heatmap.map((h) => (
              <div key={h.stage} className={`heat-cell ${h.level.toLowerCase()}`}>
                <span className="heat-name">{h.stage.replace(/_/g, ' ').slice(0, 12)}</span>
                <b>{h.waiting}</b>
              </div>
            ))}
            {heat.primary_bottleneck && (
              <span className="muted"> ← bottleneck: <b>{heat.primary_bottleneck.replace(/_/g, ' ')}</b></span>
            )}
          </div>
        )}
      </Card>

      <Card>
        <h3>🧭 Operations intelligence <span className="muted">(AI capacity plan · model health · trust · insider review)</span></h3>
        {cap && (
          <div className="grid4">
            <Stat label="Expected farmers" value={cap.expected_farmers} />
            <Stat label="Expected volume" value={`${cap.expected_quantity_mt} MT`} />
            <Stat label="Peak window" value={cap.expected_peak_window} />
            <Stat label="AI staffing plan" value={`${cap.recommended_counters} counters`}
                  sub={`${cap.recommended_staff} staff · ${cap.recommended_slot_capacity} slots`} tone="ok" />
          </div>
        )}
        {mh && (
          <p className="muted" style={{ marginTop: 8 }}>
            📈 Model health: ETA accuracy <b>{mh.eta_accuracy_pct ?? '—'}%</b> · MAE {mh.mae_minutes ?? '—'} min · {mh.samples} samples · {mh.retrain_policy}
          </p>
        )}
        {trust && (
          <p className="muted">⭐ Trust score: <b>{trust.trust_score}/100</b> — queue {trust.components.queue_efficiency_pct}% · payment {trust.components.payment_reliability_pct}% · resolution {trust.components.complaint_resolution_pct}% · farmer rating {trust.components.farmer_rating}/5</p>
        )}
        <div className="anomaly" style={{ marginTop: 8 }}>
          <b>🕵 Insider-threat review feed</b>
          {(ins?.alerts || []).length === 0 && <div className="muted">No behavioural anomalies — staff activity within normal patterns.</div>}
          {(ins?.alerts || []).map((a, i) => (
            <div key={i} className="muted">⚠ {a.actor}: {a.detail} — severity {a.severity}. {a.recommendation}</div>
          ))}
        </div>
      </Card>

      <Card>
        <h3>📱 CSC / agent booking <span className="muted">(adoption path — booked on farmer's behalf)</span></h3>
        <div className="grid4">
          <div><label>Farmer name</label><input value={agent.name} onChange={(e) => setAgent({ ...agent, name: e.target.value })} placeholder="Farmer name" /></div>
          <div><label>Phone</label><input value={agent.phone} onChange={(e) => setAgent({ ...agent, phone: e.target.value.replace(/\D/g, '').slice(0, 10) })} placeholder="10 digits" /></div>
          <div><label>Slot</label><input value={agent.slot} onChange={(e) => setAgent({ ...agent, slot: e.target.value })} placeholder="14:00" /></div>
          <div style={{ display: 'flex', alignItems: 'flex-end' }}>
            <button className="primary" style={{ marginTop: 0 }} disabled={agent.phone.length !== 10 || !agent.name}
                    onClick={async () => {
                      try {
                        const r = await api.post('/staff/agent-book', {
                          farmer_name: agent.name, phone: agent.phone, slot_time: agent.slot,
                        })
                        alert(`Booked ${r.token} for ${agent.slot} — SMS confirmation queued`)
                        setAgent({ name: '', phone: '', slot: '14:00' })
                        await load()
                      } catch (e) { setErr(e.message) }
                    }}>Book for farmer</button>
          </div>
        </div>
      </Card>

      <Card>
        <h3>💬 Live SMS / IVR channel feed <span className="muted">(every message the system has sent)</span></h3>
        <div className="channel-feed">
          {channels.length === 0 && <p className="muted">No messages yet.</p>}
          {channels.map((n, i) => (
            <div key={i} className={`feed-row ${n.channel.toLowerCase()}`}>
              <span className="feed-chan">{n.channel === 'IVR' ? '📞' : '💬'} {n.channel}</span>
              <span className="feed-body">{n.body}</span>
              <span className="feed-time muted">{n.created_at?.slice(11, 16)}</span>
            </div>
          ))}
        </div>
        {dash && (
          <p className="muted" style={{ marginTop: 8 }}>
            🤖 Wait-time model: {dash.ml?.training?.mode || 'analytic-fallback'}
            {dash.ml?.training?.r2 != null && ` · R² ${dash.ml.training.r2}`} · {dash.ml?.training?.samples ?? 0} training samples
          </p>
        )}
      </Card>

      <Card>
        <h3>📋 {t.queue}</h3>
        <table className="queue-table">
          <thead>
            <tr><th>Token</th><th>Farmer</th><th>Crop</th><th>Status</th><th>Pos</th><th>ETA</th><th>Actions</th></tr>
          </thead>
          <tbody>
            {(queue?.queue || []).map((q) => (
              <tr key={q.ticket_id}>
                <td><b>{q.token}</b>{q.priority < 0 ? ' ↩' : ''}</td>
                <td>{q.farmer_name}</td>
                <td>{q.crop} · {q.quantity_kg}kg</td>
                <td><span className={`stage-badge sm ${q.status.toLowerCase()}`}>{q.status.replace('_', ' ')}</span></td>
                <td>{q.queue_group === 'SERVING' ? 'now' : q.position}</td>
                <td>{q.eta_minutes != null ? `${q.eta_minutes}m` : '—'}
                  {q.eta_delta != null && Math.abs(q.eta_delta) >= 1 && (
                    <span className={`delta ${q.eta_delta > 0 ? 'down' : 'up'}`}>{q.eta_delta > 0 ? '⬇' : '⬆'}{Math.abs(q.eta_delta)}</span>
                  )}
                  {q.risk_band === 'HIGH' && <span className="risk high" title={(q.risk_reasons || []).join(', ')}>⚠ {Math.round((q.no_show_risk || 0) * 100)}%</span>}
                  {q.risk_band === 'MEDIUM' && <span className="risk med" title={(q.risk_reasons || []).join(', ')}>{Math.round((q.no_show_risk || 0) * 100)}%</span>}
                </td>
                <td className="actions">
                  {q.status === 'SLOT_BOOKED' && <button className="mini" onClick={() => act('/staff/checkin', { token: q.token })}>{t.checkIn}</button>}
                  {q.status === 'ARRIVED' && <button className="mini" onClick={() => act('/staff/start-weighing', { token: q.token })}>{t.weigh}</button>}
                  {q.status === 'WEIGHING' && <button className="mini" onClick={() => act('/staff/start-quality', { token: q.token })}>{t.quality}</button>}
                  {q.status === 'QUALITY_CHECK' && <button className="mini" onClick={() => act('/staff/complete-procurement', { token: q.token, quality_grade: 'A' })}>{t.approve}</button>}
                  {q.status === 'PAYMENT' && q.payment_status !== 'COMPLETED' && <button className="mini" onClick={() => act('/staff/complete-payment', { token: q.token })}>{t.pay}</button>}
                  {['SLOT_BOOKED', 'ARRIVED'].includes(q.status) && <button className="mini danger" onClick={() => act('/staff/no-show', { token: q.token, requeue: false })}>{t.checkout}</button>}
                  {q.status === 'NO_SHOW' && <button className="mini" onClick={() => act('/staff/requeue', { token: q.token })}>↩ Requeue</button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {(queue?.no_shows_today || []).length > 0 && (
          <div style={{ marginTop: 10 }}>
            <b>🚶‍♂️ Today's no-shows ({queue.no_shows_today.length})</b>
            <p className="muted" style={{ fontSize: '0.8rem' }}>Marked absent — requeue to bring them back into the live queue (behind arrivals, ahead of walk-ins).</p>
            {queue.no_shows_today.map((n) => (
              <div key={n.token} className="counter-row">
                <span className="muted"><b>{n.token}</b> · {n.farmer_name} · {n.crop} {n.quantity_kg}kg · at {n.no_shown_at?.slice(11, 16)}</span>
                <button className="mini" onClick={() => act('/staff/requeue', { token: n.token })}>↩ Requeue</button>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  )
}

// ------------------------------ Admin view --------------------------------- //

function AdminView({ lang }) {
  const t = STR[lang]
  const [jwt, setJwt] = useState(sessionStorage.getItem('mm_jwt') || '')
  const [u, setU] = useState('admin')
  const [p, setP] = useState('')
  const [cc, setCc] = useState(null)
  const [impact, setImpact] = useState(null)
  const [brain, setBrain] = useState(null)
  const [err, setErr] = useState('')

  useEffect(() => {
    if (!jwt) return
    const load = () => {
      api.get('/admin/command-centre', jwt).then(setCc).catch((e) => setErr(e.message))
      api.get('/impact').then(setImpact).catch(() => {})
      api.get('/admin/network-brain', jwt).then(setBrain).catch(() => {})
    }
    load()
    const iv = setInterval(load, 10000)
    return () => clearInterval(iv)
  }, [jwt])

  const login = async () => {
    try {
      const r = await api.post('/staff/login', { username: u, password: p })
      setJwt(r.access_token); sessionStorage.setItem('mm_jwt', r.access_token)
    } catch (e) { setErr(e.message) }
  }

  if (!jwt) {
    return (
      <Card className="hero narrow fade-in">
        <h2>🗺 {t.commandCentre}</h2>
        <label>{t.username}</label><input value={u} onChange={(e) => setU(e.target.value)} />
        <label>{t.password}</label><input type="password" value={p} onChange={(e) => setP(e.target.value)} placeholder="admin123" />
        <button className="primary big" onClick={login}>Login</button>
        {err && <p className="error">{err}</p>}
      </Card>
    )
  }

  return (
    <div className="fade-in">
      <div className="row-btns spread">
        <h2>🗺 {t.commandCentre}</h2>
        <div>
          <button className="ghost" onClick={async () => {
            try {
              const r = await api.post('/admin/demo/district', {}, jwt)
              alert(`🎬 District demo loaded: congestion + live movement in every centre · ${r.farmers_warned} at-home farmer(s) warned by the prevention sweep`)
            } catch (e) { setErr(e.message) }
          }}>🎬 District demo</button>
          <button className="ghost" onClick={() => { sessionStorage.clear(); setJwt('') }}>⎋</button>
        </div>
      </div>
      {cc && (
        <>
          <div className="grid4">
            <Stat label="Mandis monitored" value={cc.mandis_monitored} />
            <Stat label="🟢 Normal" value={cc.normal} tone="ok" />
            <Stat label="🟡 Moderate" value={cc.moderate} tone="warn" />
            <Stat label="🔴 Congested" value={cc.congested} tone={cc.congested ? 'bad' : ''} />
            <Stat label="Farmers today" value={cc.totals.farmers_today} />
            <Stat label="Completed" value={cc.totals.completed} tone="ok" />
            <Stat label="Pending payments" value={cc.totals.pending_payments} tone={cc.totals.pending_payments ? 'warn' : ''} />
            <Stat label="Receipt chain" value={cc.receipt_chain.verified ? '✅ verified' : '⚠ broken'} tone={cc.receipt_chain.verified ? 'ok' : 'bad'} />
            {impact && <Stat label="Farmer-hours saved today" value={`${impact.farmer_hours_saved_today}h`} tone="ok" />}
            {impact && <Stat label="Avg time at centre" value={`${impact.per_mandi?.[0]?.avg_time_in_mandi_min ?? '—'}m`} />}
          </div>
          {brain && (
            <Card>
              <h3>🧠 National Mandi Brain <span className="muted">(tomorrow's problems, today's actions)</span></h3>
              <div className="grid4">
                <Stat label="Centres monitored" value={brain.summary.monitored} />
                <Stat label="Overloaded tomorrow" value={brain.summary.overloaded_tomorrow} tone={brain.summary.overloaded_tomorrow ? 'bad' : 'ok'} />
                <Stat label="Underutilized" value={brain.summary.underutilized} tone="warn" />
                <Stat label="Payment hotspots" value={brain.summary.payment_hotspots} tone={brain.summary.payment_hotspots ? 'bad' : 'ok'} />
              </div>
              {brain.actions.length > 0 && (
                <div className="advice">
                  {brain.actions.map((a, i) => <p key={i} className="advice-line">→ {a}</p>)}
                </div>
              )}
              <p className="muted" style={{ fontSize: '0.75rem' }}>{brain.note}</p>
            </Card>
          )}
          <MandiMap centres={cc.centres} />
          <Card>
            <h3>Centres</h3>
            <table className="queue-table">
              <thead><tr><th>Mandi</th><th>Queue</th><th>Avg wait</th><th>Processed</th><th>Congestion</th><th>Anomalies</th></tr></thead>
              <tbody>
                {cc.centres.map((c) => (
                  <tr key={c.mandi_id}>
                    <td><b>{c.name}</b><div className="muted">{c.district}</div></td>
                    <td>{c.queue_length}</td>
                    <td>{c.avg_wait}m</td>
                    <td>{c.processed_today}</td>
                    <td>{c.congestion === 'HIGH' ? '🔴' : c.congestion === 'MODERATE' ? '🟡' : '🟢'} {c.congestion}</td>
                    <td>{c.anomaly_flags || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </>
      )}
    </div>
  )
}

// Lightweight map: plots mandi dots on a Leaflet map when CDN is reachable,
// with a clean CSS fallback grid when offline.
function MandiMap({ centres }) {
  const ref = useRef(null)
  const [cdnOk, setCdnOk] = useState(false)

  useEffect(() => {
    let map
    const css = document.createElement('link'); css.rel = 'stylesheet'
    css.href = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css'
    document.head.appendChild(css)
    const js = document.createElement('script')
    js.src = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js'
    js.onload = () => {
      setCdnOk(true)
      if (!ref.current) return
      map = window.L.map(ref.current).setView([10.4, 76.3], 8)
      window.L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: '© OpenStreetMap' }).addTo(map)
      centres.forEach((c) => {
        const color = c.congestion === 'HIGH' ? '#d93025' : c.congestion === 'MODERATE' ? '#f9ab00' : '#188038'
        window.L.circleMarker([c.lat, c.lng], { radius: 14 + c.queue_length, color, fillColor: color, fillOpacity: 0.5 })
          .addTo(map)
          .bindPopup(`<b>${c.name}</b><br/>Queue: ${c.queue_length} · ${c.congestion}<br/>Avg wait: ${c.avg_wait}m`)
      })
    }
    js.onerror = () => setCdnOk(false)
    document.head.appendChild(js)
    return () => { map?.remove?.() }
  }, [centres])

  return (
    <Card>
      <h3>📍 Mandi congestion map</h3>
      <div ref={ref} className="map" style={{ display: cdnOk ? 'block' : 'none' }} />
      {!cdnOk && (
        <div className="map-fallback">
          {centres.map((c) => (
            <div key={c.mandi_id} className={`map-chip ${c.congestion.toLowerCase()}`}>
              {c.congestion === 'HIGH' ? '🔴' : c.congestion === 'MODERATE' ? '🟡' : '🟢'} <b>{c.name}</b> — {c.queue_length} in queue
            </div>
          ))}
        </div>
      )}
    </Card>
  )
}

function AssistantChat({ open, setOpen, chat, chatQ, setChatQ, ask }) {
  if (!open) return null
  return (
    <div className="chat-panel">
      <div className="chat-head">
        <b>🤖 Mandi Mitra Assistant</b>
        <button className="mini" onClick={() => setOpen(false)}>×</button>
      </div>
      <div className="chat-body">
        {chat.map((m, i) => (
          <div key={i} className={`chat-msg ${m.role === 'you' ? 'you' : 'bot'}`}>{m.text}</div>
        ))}
      </div>
      <div className="chat-quick">
        {["When is my turn?", "What documents do I need?", "Why is my payment pending?", "Least crowded centre?"].map((q) => (
          <button key={q} className="mini" onClick={() => ask(q)}>{q}</button>
        ))}
      </div>
      <div className="chat-input">
        <input value={chatQ} onChange={(e) => setChatQ(e.target.value)}
               onKeyDown={(e) => e.key === 'Enter' && ask(chatQ)} placeholder="Ask anything…" />
        <button className="mini" onClick={() => ask(chatQ)}>Send</button>
      </div>
    </div>
  )
}

// ------------------------------ Hall board --------------------------------- //

function BoardView() {
  const [data, setData] = useState(null)
  const [mandiId, setMandiId] = useState('KL-KOCHI-01')

  useEffect(() => {
    const load = () => api.get(`/board/${mandiId}`).then(setData).catch(() => {})
    load()
    const iv = setInterval(load, 5000)
    return () => clearInterval(iv)
  }, [mandiId])

  return (
    <div className="fade-in">
      <Card className="hero">
        <div className="row-btns spread">
          <h2>📺 Now Serving — {data?.mandi_name || ''}</h2>
          <select value={mandiId} onChange={(e) => setMandiId(e.target.value)} style={{ maxWidth: 260 }}>
            <option value="KL-KOCHI-01">Kochi Central</option>
            <option value="KL-THRIS-02">Thrissur</option>
            <option value="KL-PALAK-03">Palakkad</option>
          </select>
        </div>
        <div className="grid2">
          <div>
            <h3>🔴 At counters</h3>
            {(data?.now_serving || []).length === 0 && <p className="muted">—</p>}
            {(data?.now_serving || []).map((s) => (
              <div key={s.token} className="board-token serving">{s.token}<span className="muted"> {s.stage.replace('_', ' ')}</span></div>
            ))}
          </div>
          <div>
            <h3>⏭ Next up</h3>
            {(data?.next_up || []).map((s) => (
              <div key={s.token} className="board-token">{s.token}<span className="muted"> pos {s.position} · ~{s.eta_minutes}m</span></div>
            ))}
          </div>
        </div>
        <p className="muted center">{data?.queue_length ?? '—'} farmers in queue · auto-refreshes every 5s</p>
      </Card>
    </div>
  )
}

// ------------------------------ Shell --------------------------------------- //

export default function App() {
  const [lang, setL] = useState(getLang())
  const [view, setView] = useState('farmer')
  const t = STR[lang]

  return (
    <div className="app">
      <header>
        <div className="brand" onClick={() => setView('farmer')}>
          🌾 <b>{t.appName}</b> <span className="tagline">{t.tagline}</span>
        </div>
        <nav>
          {['farmer', 'staff', 'admin', 'board'].map((v) => (
            <button key={v} className={`nav-btn ${view === v ? 'on' : ''}`} onClick={() => setView(v)}>
              {v === 'farmer' ? '👨‍🌾 Farmer' : v === 'staff' ? '🖥 Staff' : v === 'admin' ? '🗺 Admin' : '📺 Board'}
            </button>
          ))}
          <select className="lang-sel" value={lang} onChange={(e) => { setL(e.target.value); setLang(e.target.value) }}>
            {LANGS.map(([code, label]) => <option key={code} value={code}>{label}</option>)}
          </select>
        </nav>
      </header>
      <main>
        {view === 'farmer' && <FarmerView key={'f' + lang} lang={lang} />}
        {view === 'staff' && <StaffView lang={lang} onLogout={() => setView('farmer')} />}
        {view === 'admin' && <AdminView lang={lang} />}
        {view === 'board' && <BoardView />}
      </main>
      <footer>Mandi Mitra · SIH prototype · simulated SMS/IVR & payment gateways</footer>
    </div>
  )
}
