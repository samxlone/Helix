const state = {
  me: null,
  guilds: [],
  selected: null,
  page: 'overview',
  settings: null,
  originalSettings: null,
  hasUnsavedChanges: false,
  searchQuery: '',
  view: 'landing', // 'landing' | 'servers' | 'server'
  simChannel: 'music', // 'music' | 'antinuke' | 'tickets' | 'ai' | 'logs'
  activeCmd: 'play',
  activeEq: 'bass',
  isPlaying: true,
  musicTrackIdx: 0,
  musicVol: 85,
  simTickets: [],
  simAiMessages: [
    {
      sender: 'Helix AI',
      isBot: true,
      botBadge: 'GEMINI PRO',
      time: '3:30 AM',
      embed: {
        title: '🤖 Helix Neural Assistant',
        desc: 'I am your server’s contextual AI intelligence engine powered by Google Gemini & Groq. Ask me anything about server configuration, moderation policies, or command syntax!',
        fields: [
          { name: 'Model Engine', val: 'Gemini 2.5 Flash / Groq Llama-3' },
          { name: 'Server Context', val: 'Active & Channel-Bound' }
        ]
      }
    }
  ],
  simLogItems: [
    { time: '03:34:12', event: 'MESSAGE_DELETE', desc: 'Message deleted in #general by @Alex (Logged to #messages-log)', color: 'danger' },
    { time: '03:30:02', event: 'MEMBER_JOIN', desc: '@CyberSam joined the server (Logged to #joins-leaves)', color: 'good' },
    { time: '03:25:19', event: 'ROLE_UPDATE', desc: 'Assigned @VIP role to @Divyam (Logged to #roles-log)', color: 'brand' },
    { time: '03:18:40', event: 'VOICE_JOIN', desc: '@Sam joined voice channel #general-lounge (Logged to #voice-log)', color: 'brand' }
  ],
  activeThreat: 'channel_deletion',
  embedStudio: {
    title: '✨ Welcome to Helix Community',
    desc: 'Enjoy 24/7 lossless music, zero-tolerance anti-nuke defense, 10-channel logging, and custom AI chat.',
    color: '#E11D48',
    footer: 'Helix Engine • v2.5 PRO',
    author: 'Helix Systems'
  }
};

const attackScenarios = {
  channel_deletion: {
    title: 'Mass Channel Deletion Raid',
    attacker: '@RogueAdmin (Admin ID: 849204)',
    severity: 'CRITICAL',
    vector: 'Triggered deletion on #announcements & #rules',
    logs: [
      { time: '0.000s', msg: 'Rogue Admin triggers deletion of channel #announcements', type: 'warn' },
      { time: '0.014s', msg: 'Helix Anti-Nuke Sentinel flags unauthorized deletion (Threshold: 1 action)', type: 'danger' },
      { time: '0.022s', msg: 'Rogue Admin quarantined & permissions revoked (Server Lockdown active)', type: 'danger' },
      { time: '0.034s', msg: 'Auto-Recovery Engine invoked: Cloning #announcements with original permissions & position', type: 'good' },
      { time: '0.041s', msg: 'Restoration complete! Security audit sent to #mod-logs • 0 data lost', type: 'good' }
    ]
  },
  mass_ban: {
    title: 'Automated Mass-Ban Script Raid',
    attacker: '@CompromisedBot (Token Hijack)',
    severity: 'HIGH',
    vector: 'Attempted to ban 50 server members per second',
    logs: [
      { time: '0.000s', msg: 'Compromised Bot attempts rapid ban burst on 3 members', type: 'warn' },
      { time: '0.012s', msg: 'Anti-Nuke rate limiter tripped: Exceeded 2 bans/10s threshold', type: 'danger' },
      { time: '0.020s', msg: 'Compromised Bot banned and permanently kicked from server', type: 'danger' },
      { time: '0.031s', msg: 'Mass unban rollback queued and completed for affected accounts', type: 'good' },
      { time: '0.038s', msg: 'Server shield intact. All 14,500 members protected', type: 'good' }
    ]
  },
  phishing_flood: {
    title: 'Zero-Day Scam & Phishing Link Flood',
    attacker: '@SpamRaidBot_09',
    severity: 'MEDIUM',
    vector: 'Sent 15 disguised Nitro gift scam links across 4 channels',
    logs: [
      { time: '0.000s', msg: 'Spam account posts fake "discoord-nitro-free.xyz" phishing link in #general', type: 'warn' },
      { time: '0.009s', msg: 'Helix AI Threat Scanner detects zero-day phishing heuristic match', type: 'danger' },
      { time: '0.015s', msg: 'Message instantly purged before any user could click', type: 'good' },
      { time: '0.022s', msg: 'Spammer placed in 24h timeout and domain added to server blacklist', type: 'good' }
    ]
  }
};

const embedTemplates = {
  announcement: {
    author: 'Helix Community Announcements',
    title: '✨ Official Launch: Helix v2.5 Engine',
    desc: 'We are thrilled to roll out Helix v2.5 with 24/7 lossless audio DSP, zero-tolerance anti-nuke shielding, and modular logging!',
    color: '#E11D48',
    footer: 'Helix Engine • v2.5 PRO • Today at 9:35 PM',
    thumbnail: '',
    image: '',
    fields: [
      { name: '🌐 Server Shielding', val: 'Active (Strict 0ms)', inline: true },
      { name: '🎵 Audio Bitrate', val: '24-Bit / 96kHz Lossless', inline: true },
      { name: '⚡ Web Dashboard', val: 'Fully Synchronized', inline: false }
    ],
    actionBtn: '🚀 Explore Dashboard'
  },
  giveaway: {
    author: 'Community Rewards Hub',
    title: '🎁 1-MONTH DISCORD NITRO GIVEAWAY',
    desc: 'Click the button below to enter! Winner will be picked automatically by Helix Engine when timer expires.',
    color: '#F59E0B',
    footer: 'Helix Engine • Ends in 24 Hours',
    thumbnail: '',
    image: '',
    fields: [
      { name: '🏆 Grand Prize', val: '1 Month Discord Nitro + VIP Role', inline: true },
      { name: '👑 Hosted By', val: '@Owner', inline: true },
      { name: '👥 Total Entries', val: '142 Members', inline: false }
    ],
    actionBtn: '🎉 Enter Giveaway'
  },
  rules: {
    author: 'Server Administration & Security',
    title: '📜 Official Community Rules & Guidelines',
    desc: 'Please review and adhere to our community guidelines before posting in text channels or joining voice calls.',
    color: '#5865F2',
    footer: 'Helix Security System • Rule Compliance Required',
    thumbnail: '',
    image: '',
    fields: [
      { name: '1. Respect Everyone', val: 'Harassment, hate speech, or toxicity will result in immediate timeouts.', inline: false },
      { name: '2. Zero Phishing Tolerance', val: 'Phishing domains and unauthorized invites are auto-quarantined.', inline: false }
    ],
    actionBtn: '✅ Accept Guidelines'
  },
  ticket: {
    author: 'Support & Helpdesk Desk',
    title: '🎫 Helix Customer Support & Helpdesk',
    desc: 'Need assistance with server configuration, reporting a member, or billing inquiries? Create a private ticket below.',
    color: '#10B981',
    footer: 'Helix Support Engine • 24/7 Response Time',
    thumbnail: '',
    image: '',
    fields: [
      { name: '🕒 Operating Hours', val: '24/7 Automated Support', inline: true },
      { name: '⚡ Average Response', val: '< 3 minutes', inline: true }
    ],
    actionBtn: '🎫 Open Support Ticket'
  }
};

const tracks = [
  { title: 'Lofi Cyber Beats & Synth Chill', artist: 'SynthWave Collective', duration: '3:42', progress: '62%' },
  { title: 'Midnight Neon Cityscape', artist: 'Retrowave Dreams', duration: '4:15', progress: '38%' },
  { title: 'Deep Ambient Lo-Fi Rain', artist: 'Helix Sound Lab', duration: '2:58', progress: '84%' }
];

const eqPresets = {
  flat: [12, 16, 14, 18, 15, 20, 16, 18, 14, 16, 15, 18, 14, 12],
  bass: [32, 28, 26, 22, 18, 16, 14, 12, 10, 14, 18, 22, 28, 32],
  nightcore: [10, 14, 18, 22, 26, 30, 32, 30, 28, 26, 22, 18, 14, 10],
  spatial: [20, 30, 15, 28, 14, 32, 18, 26, 12, 30, 16, 28, 14, 24],
  vocal: [8, 12, 16, 24, 32, 30, 28, 26, 22, 16, 12, 10, 8, 6]
};

const app = document.querySelector('#app');
const getStoredTheme = () => localStorage.getItem('helix_theme') || 'dark';

const setTheme = (theme) => {
  document.documentElement.setAttribute('data-theme', theme);
  localStorage.setItem('helix_theme', theme);
  const icon = document.querySelector('#theme-icon');
  if (icon) icon.textContent = theme === 'dark' ? '☀️' : '🌙';
  const txt = document.querySelector('.theme-text');
  if (txt) txt.textContent = theme === 'dark' ? 'Light' : 'Dark';
};
setTheme(getStoredTheme());

const api = async (url, options = {}) => {
  const response = await fetch(url, { headers: { 'Content-Type': 'application/json', ...(options.headers || {}) }, ...options });
  if (!response.ok) throw new Error((await response.text()) || 'Request failed');
  return response.json();
};

const esc = (v = '') => String(v ?? '').replace(/[&<>'"]/g, c => ({ '&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;' }[c]));
const avatar = (guild) => guild && guild.icon ? `<img src="https://cdn.discordapp.com/icons/${guild.id}/${guild.icon}.png?size=128" alt="">` : esc(guild?.name?.[0] || 'H');
const iconUrl = (id, hash) => hash ? `https://cdn.discordapp.com/avatars/${id}/${hash}.png?size=64` : '';

function toast(message, error = false) {
  let t = document.querySelector('.toast');
  if (!t) { t = document.createElement('div'); t.className = 'toast'; document.body.append(t); }
  t.textContent = message;
  t.classList.toggle('error', error);
  t.classList.add('show');
  clearTimeout(window.toastTimer);
  window.toastTimer = setTimeout(() => t.classList.remove('show'), 3500);
}

function markUnsaved() {
  state.hasUnsavedChanges = true;
  let bar = document.querySelector('#unsaved-bar');
  if (bar) bar.classList.add('show');
}

function clearUnsaved() {
  state.hasUnsavedChanges = false;
  let bar = document.querySelector('#unsaved-bar');
  if (bar) bar.classList.remove('show');
}

// ----------------------------------------------------
// VIEW ROUTING
// ----------------------------------------------------
function showLanding() {
  state.view = 'landing';
  render();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function showServerSelector() {
  if (!state.me?.authenticated) {
    location.href = '/auth/discord';
    return;
  }
  state.view = 'servers';
  state.selected = null;
  render();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function selectServer(guild) {
  state.view = 'server';
  state.selected = guild;
  state.page = 'overview';
  state.settings = null;
  state.hasUnsavedChanges = false;
  render();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

// ----------------------------------------------------
// RENDER DISPATCHER
// ----------------------------------------------------
function render() {
  if (state.view === 'landing') {
    renderLandingPage();
  } else if (state.view === 'servers') {
    renderServerSelectionHub();
  } else {
    renderDashboardShell();
  }
}

// ====================================================
// 1. STATE-OF-THE-ART LANDING PAGE
// ====================================================
function renderLandingPage() {
  const currentTheme = getStoredTheme();
  const inviteUrl = state.me?.bot?.invite_url || 'https://discord.com';
  const guildsCount = Number(state.me?.bot?.guilds_count || 14).toLocaleString();
  const usersCount = Number(state.me?.bot?.users_count || 14500).toLocaleString();

  app.className = 'landing-shell';
  app.innerHTML = `
    <!-- AMBIENT PARALLAX GLOW ORBS -->
    <div class="ambient-orb orb-ruby" id="orb-ruby"></div>
    <div class="ambient-orb orb-gold" id="orb-gold"></div>

    <!-- STICKY LUXURY GLASS NAVIGATION -->
    <header class="landing-header">
      <div class="landing-brand" id="brand-home">
        <span>✦</span>
        <b>helix</b>
        <small>v2.5 PRO</small>
      </div>

      <nav class="landing-nav-links">
        <a href="#simulator" class="nav-pill-link"><span class="nav-icon">✦</span> Live Client</a>
        <a href="#security-lab" class="nav-pill-link"><span class="nav-icon">🛡️</span> Defense</a>
        <a href="#features" class="nav-pill-link"><span class="nav-icon">◈</span> Modules</a>
        <a href="#audio-engine" class="nav-pill-link"><span class="nav-icon">♫</span> Audio DSP</a>
        <a href="#embed-studio" class="nav-pill-link"><span class="nav-icon">🎨</span> Studio</a>
        <a href="#telemetry" class="nav-pill-link"><span class="nav-icon">📡</span> Telemetry</a>
        <a href="#comparison" class="nav-pill-link"><span class="nav-icon">⊞</span> Matrix</a>
        <a href="#faq" class="nav-pill-link"><span class="nav-icon">?</span> FAQ</a>
      </nav>

      <div class="landing-actions">
        <a class="btn-glass" href="${inviteUrl}" target="_blank" rel="noopener" style="padding:9px 18px;font-size:12.5px;">
          Invite Bot ↗
        </a>
        <button class="btn-glow" id="header-dash-btn" style="padding:9px 20px;font-size:12.5px;">
          ${state.me?.authenticated ? 'Open Dashboard ➔' : 'Sign In ➔'}
        </button>
      </div>
    </header>

    <!-- HERO SECTION -->
    <section class="hero">
      <div class="hero-badge">
        <i></i> THE ALL-IN-ONE DISCORD POWERHOUSE ENGINE
      </div>
      <h1>
        Next-Gen Discord Engine with <br>
        <span class="grad-text">Uncompromising Speed & Shielding.</span>
      </h1>
      <p>
        Zero-tolerance Anti-Nuke defense with auto-recovery, studio-quality 24/7 lossless music, 
        granular 10-channel logging, interactive embed ticket builders, multi-model AI, and a high-performance web control center.
      </p>

      <div class="hero-btns">
        <button class="btn-glow" id="hero-dash-btn">
          🚀 Open Web Dashboard
        </button>
        <a class="btn-glass" href="${inviteUrl}" target="_blank" rel="noopener">
          ✨ Add to Discord (Free)
        </a>
      </div>

      <!-- FULL AUTHENTIC PIXEL-PERFECT DISCORD CLIENT SIMULATOR -->
      <div class="discord-sim" id="simulator">
        <div class="discord-sim-window-bar">
          <div class="discord-sim-dots">
            <span></span><span></span><span></span>
          </div>
          <div class="discord-sim-window-title">
            <span>✦ HELIX DISCORD CLIENT INTERFACE</span>
          </div>
          <div class="pill green" style="font-size:9.5px;">CONNECTED (0ms)</div>
        </div>

        <div class="discord-sim-frame">
          <!-- SIMULATED SIDEBAR -->
          <div class="discord-sim-sidebar">
            <div class="discord-server-banner-header">
              <span>✦ Helix Community</span>
              <span style="font-size:11px;color:var(--d-muted)">▾</span>
            </div>

            <div class="discord-sim-ch-list">
              <div class="discord-sim-ch-category">
                <span>TEXT CHANNELS</span>
                <span>+</span>
              </div>

              <button class="discord-sim-ch-btn ${state.simChannel === 'music' ? 'active' : ''}" data-sim-ch="music">
                <span class="hash">#</span> 🎵-now-playing
              </button>
              <button class="discord-sim-ch-btn ${state.simChannel === 'antinuke' ? 'active' : ''}" data-sim-ch="antinuke">
                <span class="hash">#</span> 🛡️-anti-nuke
              </button>
              <button class="discord-sim-ch-btn ${state.simChannel === 'tickets' ? 'active' : ''}" data-sim-ch="tickets">
                <span class="hash">#</span> 🎫-create-ticket
              </button>
              <button class="discord-sim-ch-btn ${state.simChannel === 'ai' ? 'active' : ''}" data-sim-ch="ai">
                <span class="hash">#</span> 🤖-helix-ai-chat
              </button>
              <button class="discord-sim-ch-btn ${state.simChannel === 'logs' ? 'active' : ''}" data-sim-ch="logs">
                <span class="hash">#</span> 📜-audit-log
              </button>

              ${state.simTickets.length ? `
                <div class="discord-sim-ch-category" style="margin-top:12px;">
                  <span>ACTIVE TICKETS</span>
                </div>
                ${state.simTickets.map(t => `
                  <button class="discord-sim-ch-btn ${state.simChannel === t ? 'active' : ''}" data-sim-ch="${t}" style="color:var(--good);">
                    <span class="hash">#</span> 🎫-${t}
                  </button>
                `).join('')}
              ` : ''}

              <div class="discord-sim-ch-category" style="margin-top:14px;">
                <span>VOICE CHANNELS</span>
              </div>
              <div class="discord-sim-ch-btn" style="color:var(--good);cursor:default;">
                <span>🔊</span> 24/7 Music Lounge
              </div>
            </div>
          </div>

          <!-- SIMULATED CHAT MAIN -->
          <div class="discord-sim-main">
            <div class="discord-sim-ch-topbar">
              <div class="discord-sim-ch-topbar-left">
                <span style="color:var(--d-muted);font-size:18px;">#</span>
                <span>${getChannelTitle()}</span>
                <span class="discord-sim-ch-topbar-desc">${getChannelDesc()}</span>
              </div>
              <div style="font-size:14px;color:var(--d-muted);display:flex;gap:12px;">
                <span>🔔</span><span>📌</span><span>👥</span>
              </div>
            </div>

            <div class="discord-sim-chat-feed" id="sim-chat-feed">
              ${renderSimChatContent()}
            </div>

            <!-- DISCORD CHAT INPUT -->
            <div class="discord-sim-input-area">
              <form class="discord-sim-input-box" id="sim-input-form">
                <span class="plus-icon">+</span>
                <input type="text" id="sim-chat-input" placeholder="Message #${getChannelTitle()}..." autocomplete="off">
                <button type="submit" class="discord-sim-send-btn">Send ➔</button>
              </form>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- LIVE STATS RIBBON -->
    <section class="stats-ribbon reveal-3d">
      <div class="stat-item">
        <strong class="grad-text">${guildsCount}+</strong>
        <span>Active Guilds</span>
      </div>
      <div class="stat-item">
        <strong class="grad-text">${usersCount}+</strong>
        <span>Protected Community Members</span>
      </div>
      <div class="stat-item">
        <strong class="grad-text">&lt;12ms</strong>
        <span>Voice Audio Latency</span>
      </div>
      <div class="stat-item">
        <strong class="grad-text">99.99%</strong>
        <span>Verified Engine Uptime</span>
      </div>
    </section>

    <!-- 8 CORE FEATURE SHOWCASE MODULES -->
    <section class="features-container reveal-3d" id="features">
      <div class="section-head">
        <span class="subhead">POWERFUL & EXPANSIVE</span>
        <h2>Everything Your Server Needs, Handcrafted.</h2>
        <p>Built from the ground up for massive servers, esports hubs, and thriving Discord communities.</p>
      </div>

      <div class="features-grid">
        <div class="feat-card">
          <div class="feat-card-icon">🏰</div>
          <h3>Anti-Nuke Defense Suite</h3>
          <p>Zero-tolerance 1-action trigger protection, permission revocation, auto-recovery for deleted channels/roles, and mass-ban quarantine.</p>
          <span class="feat-tag">STRICT DEFENSE</span>
        </div>

        <div class="feat-card">
          <div class="feat-card-icon">🎵</div>
          <h3>Studio-Grade Voice & Music</h3>
          <p>Continuous 24/7 radio mode, Spotify & SoundCloud streaming, DSP audio filters (Bass Boost, Nightcore, 8D), volume controls, and zero stutter.</p>
          <span class="feat-tag">24/7 LOSSLESS</span>
        </div>

        <div class="feat-card">
          <div class="feat-card-icon">🎫</div>
          <h3>Embed Ticket Builder</h3>
          <p>Interactive dropdown select menus, moderator claim renaming (<code>#oreo-15007</code>), close lifecycle routing, and one-click HTML transcripts.</p>
          <span class="feat-tag">MOD CLAIM RENAMING</span>
        </div>

        <div class="feat-card">
          <div class="feat-card-icon">🤖</div>
          <h3>Intelligent AutoMod</h3>
          <p>Anti-phishing scam domain shield, unauthorized Discord invite filtering, massive heading markdown anti-spam, and automated timeouts.</p>
          <span class="feat-tag">REAL-TIME SENTINEL</span>
        </div>

        <div class="feat-card">
          <div class="feat-card-icon">📜</div>
          <h3>10-Channel Action Logging</h3>
          <p>Granular multi-channel routing for message edits, deletions, member joins/leaves, voice movements, role changes, and channel updates.</p>
          <span class="feat-tag">FULL AUDIT TRAIL</span>
        </div>

        <div class="feat-card">
          <div class="feat-card-icon">📈</div>
          <h3>Leveling & Economy System</h3>
          <p>Message XP progression, level-reward role automation, wallet/bank net worth leaderboards, interactive server shop, and rob commands.</p>
          <span class="feat-tag">GAMIFICATION</span>
        </div>

        <div class="feat-card">
          <div class="feat-card-icon">📡</div>
          <h3>Real-Time Vanity Sniping</h3>
          <p>Continuous monitoring for desired Discord custom vanity URLs with automated private DM ping alerts the instant a vanity drops.</p>
          <span class="feat-tag">SNIPER ALERTS</span>
        </div>

        <div class="feat-card">
          <div class="feat-card-icon">🧠</div>
          <h3>Multi-Model AI Assistant</h3>
          <p>Natural conversation engine powered by Gemini, Groq, and OpenAI with custom server personas and dedicated channel integration.</p>
          <span class="feat-tag">AI INTEGRATION</span>
        </div>

        <div class="feat-card">
          <div class="feat-card-icon">👥</div>
          <h3>Intelligent Auto Roles</h3>
          <p>Instantly grant custom roles to new human members and bots on join with hierarchy safeguards and one-click configuration.</p>
          <span class="feat-tag">AUTOMATION</span>
        </div>

        <div class="feat-card">
          <div class="feat-card-icon">👋</div>
          <h3>Luxury Welcome & Goodbye</h3>
          <p>Stunning Obsidian & Crimson Pillow canvas image cards, rich embeds, leave notices, and optional onboarding private DMs.</p>
          <span class="feat-tag">CANVAS CARDS</span>
        </div>

        <div class="feat-card">
          <div class="feat-card-icon">⭐</div>
          <h3>Starboard Showcase</h3>
          <p>Pin and showcase community highlights that reach reaction milestones with author avatars, media previews, and jump links.</p>
          <span class="feat-tag">COMMUNITY PIN</span>
        </div>
      </div>
    </section>

    <!-- INTERACTIVE SECURITY SANDBOX & ANTI-NUKE SIMULATOR -->
    <section class="security-lab-section reveal-3d" id="security-lab">
      <div class="section-head">
        <span class="subhead">ZERO-TOLERANCE DEFENSE</span>
        <h2>Anti-Nuke Threat Defense Simulator</h2>
        <p>Click an attack scenario to witness Helix's sub-40ms quarantine & auto-recovery engine in action.</p>
      </div>

      <div class="security-lab-box">
        <div class="threat-selector-row">
          <button class="threat-btn ${state.activeThreat === 'channel_deletion' ? 'active' : ''}" data-threat="channel_deletion">
            🔴 Mass Channel Deletion Attack
          </button>
          <button class="threat-btn ${state.activeThreat === 'mass_ban' ? 'active' : ''}" data-threat="mass_ban">
            💀 Automated Mass-Ban Raid
          </button>
          <button class="threat-btn ${state.activeThreat === 'phishing_flood' ? 'active' : ''}" data-threat="phishing_flood">
            🔗 Phishing & Scam Domain Flood
          </button>
        </div>

        <div class="security-screen-grid">
          <div class="security-terminal-box">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;border-bottom:1px solid rgba(255,255,255,0.06);padding-bottom:10px;">
              <span style="font-size:11px;color:var(--muted);">HELIX DEFENSE SENTINEL • LIVE LOG FEED</span>
              <span class="pill danger" style="font-size:9.5px;">${attackScenarios[state.activeThreat].severity}</span>
            </div>
            <div id="threat-log-feed">
              ${attackScenarios[state.activeThreat].logs.map(l => `
                <div class="security-log-row">
                  <span class="security-log-time">[${l.time}]</span>
                  <span class="security-log-msg ${l.type}">${esc(l.msg)}</span>
                </div>
              `).join('')}
            </div>
          </div>

          <div class="security-radar-card">
            <div style="display:flex;align-items:center;gap:10px;margin-bottom:14px;">
              <span class="status-dot"></span>
              <b style="font-size:14.5px;color:#fff;">Active Threat Shield</b>
            </div>

            <div class="radar-stat-item">
              <b>Attacker Profile:</b>
              <span style="color:#fde68a;">${attackScenarios[state.activeThreat].attacker}</span>
            </div>
            <div class="radar-stat-item">
              <b>Attack Vector:</b>
              <span style="color:var(--danger);font-size:11.5px;">${attackScenarios[state.activeThreat].vector}</span>
            </div>
            <div class="radar-stat-item">
              <b>Quarantine Response Time:</b>
              <span style="color:var(--good);">&lt;24 milliseconds</span>
            </div>
            <div class="radar-stat-item">
              <b>Channel Permissions Recovered:</b>
              <span style="color:var(--good);">100% Intact</span>
            </div>

            <div style="margin-top:20px;">
              <button class="btn-glow" id="test-threat-btn" style="width:100%;padding:12px;font-size:13px;justify-content:center;">
                ⚡ Trigger Attack Simulation
              </button>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- LIVE SYSTEM TELEMETRY & CLUSTER MATRIX -->
    <section class="telemetry-section reveal-3d" id="telemetry">
      <div class="section-head">
        <span class="subhead">INFRASTRUCTURE HEALTH</span>
        <h2>High-Performance Cluster Telemetry</h2>
        <p>Real-time distributed hardware metrics, shard latency, and streaming uptime status.</p>
      </div>

      <div class="telemetry-grid">
        <div class="telemetry-card">
          <div class="telemetry-header">
            <b>Discord Gateway</b>
            <span class="pill green" style="font-size:9.5px;">HEALTHY</span>
          </div>
          <div class="telemetry-val" style="color:var(--good);">&lt;9ms</div>
          <div class="telemetry-foot">WebSocket Heartbeat Ping</div>
        </div>

        <div class="telemetry-card">
          <div class="telemetry-header">
            <b>Audio DSP Engine</b>
            <span class="pill green" style="font-size:9.5px;">ACTIVE</span>
          </div>
          <div class="telemetry-val" style="color:#fde68a;">24-Bit / 96kHz</div>
          <div class="telemetry-foot">Lossless Stereo FFmpeg Stream</div>
        </div>

        <div class="telemetry-card">
          <div class="telemetry-header">
            <b>Database Storage</b>
            <span class="pill green" style="font-size:9.5px;">WAL MODE</span>
          </div>
          <div class="telemetry-val" style="color:#60a5fa;">0.12ms</div>
          <div class="telemetry-foot">SQLite WAL Query Latency</div>
        </div>

        <div class="telemetry-card">
          <div class="telemetry-header">
            <b>Global Availability</b>
            <span class="pill green" style="font-size:9.5px;">SLA 99.99%</span>
          </div>
          <div class="telemetry-val" style="color:var(--brand-light);">99.99%</div>
          <div class="telemetry-foot">Verified Uptime Record</div>
        </div>
      </div>
    </section>

    <!-- INTERACTIVE AUDIO DSP EQUALIZER SHOWCASE -->
    <section class="audio-showcase reveal-3d" id="audio-engine">
      <div class="section-head" style="margin-bottom:28px;">
        <span class="subhead">DSP AUDIO PROCESSOR</span>
        <h2>Studio-Grade Sound Filtering</h2>
        <p>Click any preset to preview real-time hardware-accelerated sound transformations.</p>
      </div>

      <div class="eq-presets-wrap" style="justify-content:center;">
        <button class="eq-preset-btn ${state.activeEq === 'bass' ? 'active' : ''}" data-eq="bass">🔥 Bass Boost +12dB</button>
        <button class="eq-preset-btn ${state.activeEq === 'nightcore' ? 'active' : ''}" data-eq="nightcore">⚡ Nightcore Speedup</button>
        <button class="eq-preset-btn ${state.activeEq === 'spatial' ? 'active' : ''}" data-eq="spatial">🎧 8D Spatial Surround</button>
        <button class="eq-preset-btn ${state.activeEq === 'vocal' ? 'active' : ''}" data-eq="vocal">🎤 Vocal Enhancer</button>
        <button class="eq-preset-btn ${state.activeEq === 'flat' ? 'active' : ''}" data-eq="flat">🎚 Pure Studio Flat</button>
      </div>

      <div class="eq-bars-container" id="eq-spectrum">
        ${(eqPresets[state.activeEq] || eqPresets.bass).map(h => `
          <div class="eq-bar-item" style="height:${h * 3.5}px;"></div>
        `).join('')}
      </div>
    </section>

    <!-- INTERACTIVE EMBED & WEBHOOK STUDIO PLAYGROUND -->
    <section class="embed-studio-section reveal-3d" id="embed-studio">
      <div class="section-head" style="margin-bottom:24px;">
        <span class="subhead">CREATIVE STUDIO</span>
        <h2>Live Discord Embed & Webhook Studio</h2>
        <p>Design custom rich embeds with instant live Discord client preview, dynamic fields, and export.</p>
      </div>

      <div class="embed-studio-wrap">
        <div class="studio-form">
          <!-- STUDIO NAVIGATION TABS -->
          <div class="studio-tab-bar">
            <button type="button" class="studio-tab-btn ${(state.embedStudio.activeTab || 'content') === 'content' ? 'active' : ''}" data-studio-tab="content">
              📝 Content & Color
            </button>
            <button type="button" class="studio-tab-btn ${state.embedStudio.activeTab === 'fields' ? 'active' : ''}" data-studio-tab="fields">
              🧩 Fields (${state.embedStudio.fields?.length || 0})
            </button>
            <button type="button" class="studio-tab-btn ${state.embedStudio.activeTab === 'media' ? 'active' : ''}" data-studio-tab="media">
              🖼️ Media & Meta
            </button>
          </div>

          <!-- TAB 1: CONTENT & COLOR -->
          <div class="studio-tab-pane" style="display:${(state.embedStudio.activeTab || 'content') === 'content' ? 'flex' : 'none'};flex-direction:column;gap:12px;">
            <div class="studio-presets-row">
              <button class="studio-preset-btn ${state.embedStudio.template === 'announcement' ? 'active' : ''}" data-embed-template="announcement">📢 Announcement</button>
              <button class="studio-preset-btn ${state.embedStudio.template === 'giveaway' ? 'active' : ''}" data-embed-template="giveaway">🎁 Giveaway</button>
              <button class="studio-preset-btn ${state.embedStudio.template === 'rules' ? 'active' : ''}" data-embed-template="rules">📜 Rules</button>
              <button class="studio-preset-btn ${state.embedStudio.template === 'ticket' ? 'active' : ''}" data-embed-template="ticket">🎫 Support Ticket</button>
            </div>

            <div class="field" style="margin:0;">
              <label>Embed Title</label>
              <input type="text" id="studio-title" value="${esc(state.embedStudio.title)}" placeholder="Enter embed title...">
            </div>

            <div class="field" style="margin:0;">
              <label>Embed Description</label>
              <textarea id="studio-desc" rows="2" style="min-height:58px;" placeholder="Enter embed description...">${esc(state.embedStudio.desc)}</textarea>
            </div>

            <div class="field" style="margin:0;">
              <label>Accent Color</label>
              <div class="studio-color-wrap">
                <input type="color" id="studio-color" class="studio-color-swatch" value="${state.embedStudio.color}">
                <input type="text" id="studio-color-hex" value="${state.embedStudio.color}" style="width:105px;font-family:'Fira Code',monospace;" placeholder="#E11D48">
                <div class="studio-color-pills">
                  <button type="button" class="studio-color-pill" style="background:#E11D48;" data-set-color="#E11D48"></button>
                  <button type="button" class="studio-color-pill" style="background:#5865F2;" data-set-color="#5865F2"></button>
                  <button type="button" class="studio-color-pill" style="background:#10B981;" data-set-color="#10B981"></button>
                  <button type="button" class="studio-color-pill" style="background:#F59E0B;" data-set-color="#F59E0B"></button>
                  <button type="button" class="studio-color-pill" style="background:#8B5CF6;" data-set-color="#8B5CF6"></button>
                </div>
              </div>
            </div>
          </div>

          <!-- TAB 2: DYNAMIC CUSTOM FIELDS -->
          <div class="studio-tab-pane" style="display:${state.embedStudio.activeTab === 'fields' ? 'flex' : 'none'};flex-direction:column;gap:10px;">
            <div style="display:flex;justify-content:space-between;align-items:center;">
              <span style="font-size:12px;color:var(--muted);font-weight:700;">Add dynamic field grids to your embed</span>
              <button type="button" class="button secondary" id="studio-add-field-btn" style="padding:5px 12px;font-size:12px;">+ Add Field</button>
            </div>
            <div class="studio-fields-scroll" id="studio-fields-list">
              ${(state.embedStudio.fields || []).map((f, i) => `
                <div class="studio-field-item" data-field-idx="${i}">
                  <input type="text" class="studio-f-name" value="${esc(f.name)}" placeholder="Field Title">
                  <input type="text" class="studio-f-val" value="${esc(f.val)}" placeholder="Field Content">
                  <label class="studio-checkbox-label">
                    <input type="checkbox" class="studio-f-inline" ${f.inline ? 'checked' : ''}> Inline
                  </label>
                  <button type="button" class="studio-del-field-btn" data-del-f="${i}" title="Delete Field">✕</button>
                </div>
              `).join('')}
            </div>
          </div>

          <!-- TAB 3: MEDIA & META -->
          <div class="studio-tab-pane" style="display:${state.embedStudio.activeTab === 'media' ? 'flex' : 'none'};flex-direction:column;gap:12px;">
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
              <div class="field" style="margin:0;">
                <label>Author Name</label>
                <input type="text" id="studio-author" value="${esc(state.embedStudio.author)}" placeholder="e.g. Helix Announcements">
              </div>
              <div class="field" style="margin:0;">
                <label>Footer Text</label>
                <input type="text" id="studio-footer" value="${esc(state.embedStudio.footer)}" placeholder="Footer text...">
              </div>
            </div>

            <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
              <div class="field" style="margin:0;">
                <label>Thumbnail URL (Optional)</label>
                <input type="text" id="studio-thumbnail" value="${esc(state.embedStudio.thumbnail || '')}" placeholder="https://...">
              </div>
              <div class="field" style="margin:0;">
                <label>Banner Image URL (Optional)</label>
                <input type="text" id="studio-image" value="${esc(state.embedStudio.image || '')}" placeholder="https://...">
              </div>
            </div>
          </div>

          <!-- EXPORT ACTIONS -->
          <div style="display:flex;gap:10px;margin-top:6px;">
            <button class="btn-glow" id="studio-copy-json" style="flex:1;padding:10px;font-size:12.5px;justify-content:center;">
              📋 Copy JSON
            </button>
            <button class="btn-glass" id="studio-copy-md" style="flex:1;padding:10px;font-size:12.5px;justify-content:center;">
              ✨ Copy Markdown
            </button>
          </div>
        </div>

        <!-- AUTHENTIC DISCORD CLIENT PREVIEW -->
        <div class="studio-preview-box">
          <div class="studio-preview-topbar">
            <div style="display:flex;align-items:center;gap:8px;font-weight:800;font-size:13.5px;color:var(--d-header);">
              <span style="color:var(--d-muted);font-weight:400;font-size:16px;">#</span> announcements
            </div>
            <div style="font-size:11px;color:var(--d-muted);display:flex;gap:8px;">
              <span>🔔</span><span>📌</span><span>👥</span>
            </div>
          </div>

          <div class="studio-preview-feed">
            <div class="studio-msg-row">
              <div class="d-avatar" style="background:var(--brand);width:38px;height:38px;font-size:15px;">✦</div>
              <div style="flex:1;min-width:0;">
                <div class="d-msg-header">
                  <span class="d-author">Helix</span>
                  <span class="d-bot-badge">BOT ✓</span>
                  <span class="d-timestamp">Today at 9:35 PM</span>
                </div>

                <!-- THE EMBED -->
                <div class="d-embed" id="studio-live-embed" style="border-left-color:${state.embedStudio.color};margin:6px 0 0;max-width:100%;">
                  ${state.embedStudio.author ? `
                    <div class="d-embed-author" id="studio-prev-author">${esc(state.embedStudio.author)}</div>
                  ` : ''}
                  <div class="d-embed-title" id="studio-prev-title">${esc(state.embedStudio.title)}</div>
                  <div class="d-embed-desc" id="studio-prev-desc">${esc(state.embedStudio.desc)}</div>

                  <!-- FIELDS GRID -->
                  <div class="d-embed-fields" id="studio-prev-fields" style="grid-template-columns:${state.embedStudio.fields?.some(f => f.inline) ? 'repeat(2, 1fr)' : '1fr'};">
                    ${(state.embedStudio.fields || []).map(f => `
                      <div class="d-embed-field" style="${f.inline ? '' : 'grid-column: 1 / -1;'}">
                        <b>${esc(f.name)}</b>
                        <span>${esc(f.val)}</span>
                      </div>
                    `).join('')}
                  </div>

                  ${state.embedStudio.image ? `
                    <div id="studio-prev-img-wrap" style="margin-top:10px;border-radius:6px;overflow:hidden;">
                      <img src="${esc(state.embedStudio.image)}" style="width:100%;max-height:240px;object-fit:cover;" alt="">
                    </div>
                  ` : ''}

                  <div class="d-embed-footer" id="studio-prev-footer">
                    <span>${esc(state.embedStudio.footer)}</span>
                  </div>
                </div>

                <!-- ACTION BUTTONS ROW -->
                <div class="d-action-row" id="studio-prev-action-row" style="margin-top:10px;">
                  <button type="button" class="d-btn d-btn-primary">${esc(state.embedStudio.actionBtn || '🚀 Action Button')}</button>
                  <button type="button" class="d-btn d-btn-secondary">Dismiss</button>
                </div>
              </div>
            </div>
          </div>

          <div class="studio-preview-bottom">
            <span>Live Interactive Preview</span>
            <span style="color:var(--good);font-weight:700;">● Pixel-Perfect Discord Client</span>
          </div>
        </div>
      </div>
    </section>

    <!-- FEATURE COMPARISON MATRIX TABLE -->
    <section class="comparison-section reveal-3d" id="comparison">
      <div class="section-head">
        <span class="subhead">THE COMPETITIVE EDGE</span>
        <h2>Why Top Communities Choose Helix</h2>
        <p>Compare Helix side-by-side against standard public Discord bots.</p>
      </div>

      <div class="comp-table-wrap">
        <table class="comp-table">
          <thead>
            <tr>
              <th>FEATURE / CAPABILITY</th>
              <th class="helix-col">✦ HELIX ENGINE</th>
              <th>GENERIC PUBLIC BOTS</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td><b>24/7 Lossless Voice & Music</b></td>
              <td class="helix-col">✓ Included 100% Free (Zero Lag)</td>
              <td>❌ Locked Behind $10/mo Paywall</td>
            </tr>
            <tr>
              <td><b>Strict Anti-Nuke & Auto Recovery</b></td>
              <td class="helix-col">✓ Instant Ban & Auto-Clones Deleted Channels</td>
              <td>❌ Delayed Alerts / No Channel Restoral</td>
            </tr>
            <tr>
              <td><b>Multi-Channel Event Logging</b></td>
              <td class="helix-col">✓ 10 Specialized Distinct Channels</td>
              <td>❌ Single Cluttered Channel Only</td>
            </tr>
            <tr>
              <td><b>Embed Ticket Builder</b></td>
              <td class="helix-col">✓ Interactive Visual Embed Builder in Discord</td>
              <td>❌ Basic Plain Buttons or External Site</td>
            </tr>
            <tr>
              <td><b>Multi-Model AI Assistant</b></td>
              <td class="helix-col">✓ Gemini, Groq, OpenAI with Context</td>
              <td>❌ Paid or Generic Static Responses</td>
            </tr>
            <tr>
              <td><b>Self-Hosted Web Dashboard</b></td>
              <td class="helix-col">✓ Included & Runs with Your Bot Instance</td>
              <td>❌ Public Shared Cloud (Slow)</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- COMMAND PLAYGROUND TERMINAL -->
    <section class="terminal-section reveal-3d" id="commands">
      <div class="section-head">
        <span class="subhead">INSTANT PLAYGROUND</span>
        <h2>Interactive Command Reference</h2>
        <p>Test Discord bot commands and view live rich embed rendering.</p>
      </div>

      <div class="terminal-box">
        <div class="terminal-head">
          <span class="status-dot"></span>
          <span style="font-size:12px;font-family:'Fira Code',monospace;color:var(--muted)">helix-terminal @ v2.5</span>
        </div>
        <div class="cmd-chips">
          ${['play', 'ticket builder', 'snipe', 'autorole add @Members', 'setwelcome #welcome', 'setstarboard #starboard', 'stats', 'antinuke strict on', 'setlog', 'rank', 'ask'].map(c => `
            <button class="cmd-chip ${state.activeCmd === c ? 'active' : ''}" data-cmd="${c}">!${c}</button>
          `).join('')}
        </div>
        <div class="terminal-content" id="terminal-preview">
          ${renderCommandPreview(state.activeCmd)}
        </div>
        <div style="display:flex;justify-content:flex-end;margin-top:12px;">
          <button class="button secondary" id="copy-cmd-btn" style="padding:6px 14px;font-size:12px;">📋 Copy Command</button>
        </div>
      </div>
    </section>

    <!-- FAQ ACCORDION -->
    <section class="faq-section reveal-3d" id="faq">
      <div class="section-head">
        <span class="subhead">FREQUENTLY ASKED QUESTIONS</span>
        <h2>Got Questions? We Have Answers.</h2>
      </div>

      <div class="faq-item active">
        <button class="faq-question">How do I invite Helix to my Discord server? <span>▾</span></button>
        <div class="faq-answer">Click the <b>Invite Bot</b> button at the top of the page. Select your server and grant Administrator permissions to ensure Anti-Nuke, logging, and music features work smoothly.</div>
      </div>

      <div class="faq-item">
        <button class="faq-question">Is 24/7 continuous music playback really free? <span>▾</span></button>
        <div class="faq-answer">Yes! Helix provides full 24/7 mode (<code>!247</code>) without paywalls, supporting Spotify, SoundCloud, YouTube, and direct audio streams with zero latency.</div>
      </div>

      <div class="faq-item">
        <button class="faq-question">How does Strict Anti-Nuke Auto-Recovery work? <span>▾</span></button>
        <div class="faq-answer">When Strict Mode is active, any unwhitelisted admin who deletes a channel, mass-bans members, or alters permissions is banned within 0.04s, and Helix instantly clones the deleted channel with all previous role permissions intact!</div>
      </div>

      <div class="faq-item">
        <button class="faq-question">Can I customize the Ticket Panel and options? <span>▾</span></button>
        <div class="faq-answer">Yes! Run <code>!ticket builder</code> or <code>/ticket builder</code> in Discord to launch the visual modal builder, where you can customize embed titles, colors, banners, and add/edit/delete category select options in real time.</div>
      </div>
    </section>

    <!-- CTA BANNER -->
    <section class="cta-banner reveal-3d">
      <h2>Ready to transform your Discord server?</h2>
      <p>Empower your moderation team and entertain your community with the ultimate all-in-one Discord bot.</p>
      <div style="display:flex;justify-content:center;gap:16px;flex-wrap:wrap;">
        <button class="btn-glow" id="cta-dash-btn">🚀 Launch Web Dashboard</button>
        <a class="btn-glass" href="${inviteUrl}" target="_blank" rel="noopener">✨ Add Helix to Discord</a>
      </div>
    </section>

    <!-- FOOTER -->
    <footer class="landing-footer">
      <div>
        <span class="status-dot"></span>
        <span><b>Helix Bot</b> · Next-Gen Discord Engine © 2026</span>
      </div>
      <div>
        <a href="#simulator">Simulator</a>
        <a href="#security-lab">Defense Lab</a>
        <a href="#features">Features</a>
        <a href="#embed-studio">Embed Studio</a>
        <a href="${inviteUrl}" target="_blank" rel="noopener">Invite</a>
        <a href="#" id="footer-dash-link">Dashboard</a>
      </div>
    </footer>

    <!-- MOBILE FLOATING BOTTOM DOCK -->
    <div class="mobile-bottom-dock">
      <a href="#simulator" class="mobile-dock-link">
        <span>⚡</span>
        <span>Client</span>
      </a>
      <a href="#security-lab" class="mobile-dock-link">
        <span>🛡️</span>
        <span>Defense</span>
      </a>
      <a href="#features" class="mobile-dock-link">
        <span>◈</span>
        <span>Modules</span>
      </a>
      <a href="#embed-studio" class="mobile-dock-link">
        <span>🎨</span>
        <span>Studio</span>
      </a>
      <button class="mobile-dock-btn" id="mobile-dock-login">
        Dashboard ➔
      </button>
    </div>
  `;

  // Attach Landing Page Event Listeners
  document.querySelector('#brand-home')?.addEventListener('click', () => showLanding());
  document.querySelector('#header-dash-btn')?.addEventListener('click', () => showServerSelector());
  document.querySelector('#hero-dash-btn')?.addEventListener('click', () => showServerSelector());
  document.querySelector('#cta-dash-btn')?.addEventListener('click', () => showServerSelector());
  document.querySelector('#footer-dash-link')?.addEventListener('click', (e) => { e.preventDefault(); showServerSelector(); });

  document.querySelector('#theme-toggle')?.addEventListener('click', () => {
    const next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    setTheme(next);
  });

  // Initialize and Bind Simulated Discord Client
  bindSimChannelButtons();
  attachSimEvents();

  // Chat Input Handler
  document.querySelector('#sim-input-form')?.addEventListener('submit', (e) => {
    e.preventDefault();
    const input = document.querySelector('#sim-chat-input');
    if (!input || !input.value.trim()) return;
    const text = input.value.trim();
    input.value = '';
    handleSimUserMessage(text);
  });

  // DSP Equalizer Preset Handlers
  document.querySelectorAll('.eq-preset-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      state.activeEq = btn.dataset.eq;
      document.querySelectorAll('.eq-preset-btn').forEach(b => b.classList.toggle('active', b.dataset.eq === state.activeEq));
      const heights = eqPresets[state.activeEq] || eqPresets.bass;
      const spectrum = document.querySelector('#eq-spectrum');
      if (spectrum) {
        spectrum.innerHTML = heights.map(h => `<div class="eq-bar-item" style="height:${h * 3.5}px;"></div>`).join('');
      }
    });
  });

  // Command Playground Chip Handlers
  document.querySelectorAll('.cmd-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      state.activeCmd = chip.dataset.cmd;
      document.querySelectorAll('.cmd-chip').forEach(c => c.classList.toggle('active', c.dataset.cmd === state.activeCmd));
      const termEl = document.querySelector('#terminal-preview');
      if (termEl) termEl.innerHTML = renderCommandPreview(state.activeCmd);
    });
  });

  // Security Sandbox Threat Switcher
  document.querySelectorAll('[data-threat]').forEach(btn => {
    btn.addEventListener('click', () => {
      state.activeThreat = btn.dataset.threat;
      document.querySelectorAll('[data-threat]').forEach(b => b.classList.toggle('active', b.dataset.threat === state.activeThreat));
      const scenario = attackScenarios[state.activeThreat];
      const feed = document.querySelector('#threat-log-feed');
      if (feed && scenario) {
        feed.innerHTML = scenario.logs.map(l => `
          <div class="security-log-row">
            <span class="security-log-time">[${l.time}]</span>
            <span class="security-log-msg ${l.type}">${esc(l.msg)}</span>
          </div>
        `).join('');
      }
      const attackerEl = document.querySelector('.security-radar-card .radar-stat-item:nth-child(2) span');
      if (attackerEl && scenario) attackerEl.textContent = scenario.attacker;
      const vectorEl = document.querySelector('.security-radar-card .radar-stat-item:nth-child(3) span');
      if (vectorEl && scenario) vectorEl.textContent = scenario.vector;
    });
  });

  // Threat test simulation button
  document.querySelector('#test-threat-btn')?.addEventListener('click', () => {
    const scenario = attackScenarios[state.activeThreat];
    toast(`🛡️ Executed Anti-Nuke defense against ${scenario.title}! 0 data lost.`);
  });

  // Embed Studio Tab Switcher
  document.querySelectorAll('[data-studio-tab]').forEach(btn => {
    btn.addEventListener('click', () => {
      state.embedStudio.activeTab = btn.dataset.studioTab;
      syncFormToState();
      renderLandingPage();
      const studioSec = document.querySelector('#embed-studio');
      if (studioSec) studioSec.scrollIntoView({ behavior: 'auto', block: 'nearest' });
    });
  });

  // Embed Studio Template Switcher
  document.querySelectorAll('[data-embed-template]').forEach(btn => {
    btn.addEventListener('click', () => {
      const tmplKey = btn.dataset.embedTemplate;
      const tmpl = embedTemplates[tmplKey];
      if (!tmpl) return;

      state.embedStudio = {
        template: tmplKey,
        activeTab: state.embedStudio.activeTab || 'content',
        author: tmpl.author,
        authorIcon: tmpl.authorIcon || '',
        title: tmpl.title,
        desc: tmpl.desc,
        color: tmpl.color,
        footer: tmpl.footer,
        thumbnail: tmpl.thumbnail || '',
        image: tmpl.image || '',
        fields: JSON.parse(JSON.stringify(tmpl.fields || [])),
        actionBtn: tmpl.actionBtn || '🚀 Action'
      };

      // Re-render landing to sync all inputs & fields cleanly
      renderLandingPage();
      const studioSec = document.querySelector('#embed-studio');
      if (studioSec) studioSec.scrollIntoView({ behavior: 'smooth', block: 'center' });
    });
  });

  // Embed Studio Live Preview Handlers
  const renderStudioLiveEmbed = () => {
    const embed = document.querySelector('#studio-live-embed');
    if (embed) embed.style.borderLeftColor = state.embedStudio.color;
    const prevAuthor = document.querySelector('#studio-prev-author');
    if (prevAuthor) {
      prevAuthor.textContent = state.embedStudio.author;
      prevAuthor.style.display = state.embedStudio.author ? 'flex' : 'none';
    }
    const prevTitle = document.querySelector('#studio-prev-title');
    if (prevTitle) prevTitle.textContent = state.embedStudio.title;
    const prevDesc = document.querySelector('#studio-prev-desc');
    if (prevDesc) prevDesc.textContent = state.embedStudio.desc;
    const prevFooter = document.querySelector('#studio-prev-footer span');
    if (prevFooter) prevFooter.textContent = state.embedStudio.footer;

    const prevFields = document.querySelector('#studio-prev-fields');
    if (prevFields) {
      prevFields.style.gridTemplateColumns = state.embedStudio.fields?.some(f => f.inline) ? 'repeat(2, 1fr)' : '1fr';
      prevFields.innerHTML = (state.embedStudio.fields || []).map(f => `
        <div class="d-embed-field" style="${f.inline ? '' : 'grid-column: 1 / -1;'}">
          <b>${esc(f.name || 'Field Title')}</b>
          <span>${esc(f.val || 'Content')}</span>
        </div>
      `).join('');
    }
  };

  const syncFormToState = () => {
    const authorInp = document.querySelector('#studio-author');
    if (authorInp) state.embedStudio.author = authorInp.value;
    const authorIconInp = document.querySelector('#studio-author-icon');
    if (authorIconInp) state.embedStudio.authorIcon = authorIconInp.value;
    const titleInp = document.querySelector('#studio-title');
    if (titleInp) state.embedStudio.title = titleInp.value;
    const descInp = document.querySelector('#studio-desc');
    if (descInp) state.embedStudio.desc = descInp.value;
    const colorInp = document.querySelector('#studio-color');
    if (colorInp) state.embedStudio.color = colorInp.value;
    const thumbInp = document.querySelector('#studio-thumbnail');
    if (thumbInp) state.embedStudio.thumbnail = thumbInp.value;
    const imgInp = document.querySelector('#studio-image');
    if (imgInp) state.embedStudio.image = imgInp.value;
    const footerInp = document.querySelector('#studio-footer');
    if (footerInp) state.embedStudio.footer = footerInp.value;

    // Collect custom fields only when fields tab is active or items exist
    const fieldItems = document.querySelectorAll('#studio-fields-list .studio-field-item');
    if (fieldItems && fieldItems.length > 0) {
      const fields = [];
      fieldItems.forEach(item => {
        const name = item.querySelector('.studio-f-name')?.value || '';
        const val = item.querySelector('.studio-f-val')?.value || '';
        const inline = item.querySelector('.studio-f-inline')?.checked || false;
        fields.push({ name, val, inline });
      });
      state.embedStudio.fields = fields;
    }

    renderStudioLiveEmbed();
  };

  // Attach input listeners
  ['#studio-author', '#studio-author-icon', '#studio-title', '#studio-desc', '#studio-thumbnail', '#studio-image', '#studio-footer'].forEach(sel => {
    document.querySelector(sel)?.addEventListener('input', syncFormToState);
  });

  // Color picker sync
  const colorInput = document.querySelector('#studio-color');
  const colorHex = document.querySelector('#studio-color-hex');
  colorInput?.addEventListener('input', () => {
    if (colorHex) colorHex.value = colorInput.value;
    syncFormToState();
  });
  colorHex?.addEventListener('input', () => {
    if (/^#[0-9A-F]{6}$/i.test(colorHex.value)) {
      if (colorInput) colorInput.value = colorHex.value;
      syncFormToState();
    }
  });

  // Preset color pills
  document.querySelectorAll('[data-set-color]').forEach(pill => {
    pill.addEventListener('click', () => {
      const hex = pill.dataset.setColor;
      if (colorInput) colorInput.value = hex;
      if (colorHex) colorHex.value = hex;
      syncFormToState();
    });
  });

  // Add Custom Field Button
  document.querySelector('#studio-add-field-btn')?.addEventListener('click', () => {
    if (!state.embedStudio.fields) state.embedStudio.fields = [];
    state.embedStudio.fields.push({ name: `Field ${state.embedStudio.fields.length + 1}`, val: 'Value', inline: true });
    
    const list = document.querySelector('#studio-fields-list');
    if (list) {
      list.innerHTML = state.embedStudio.fields.map((f, i) => `
        <div class="studio-field-item" data-field-idx="${i}">
          <input type="text" class="studio-f-name" value="${esc(f.name)}" placeholder="Field Title">
          <input type="text" class="studio-f-val" value="${esc(f.val)}" placeholder="Field Content">
          <label class="studio-checkbox-label">
            <input type="checkbox" class="studio-f-inline" ${f.inline ? 'checked' : ''}> Inline
          </label>
          <button type="button" class="studio-del-field-btn" data-del-f="${i}" title="Delete Field">✕</button>
        </div>
      `).join('');
      attachFieldEvents();
    }
    syncFormToState();
  });

  function attachFieldEvents() {
    document.querySelectorAll('#studio-fields-list input').forEach(inp => {
      inp.addEventListener('input', syncFormToState);
      inp.addEventListener('change', syncFormToState);
    });
    document.querySelectorAll('[data-del-f]').forEach(btn => {
      btn.addEventListener('click', () => {
        const idx = Number(btn.dataset.delF);
        state.embedStudio.fields.splice(idx, 1);
        renderLandingPage();
        const studioSec = document.querySelector('#embed-studio');
        if (studioSec) studioSec.scrollIntoView({ behavior: 'smooth', block: 'center' });
      });
    });
  }
  attachFieldEvents();

  document.querySelector('#studio-copy-json')?.addEventListener('click', () => {
    const jsonStr = JSON.stringify({
      embed: {
        title: state.embedStudio.title,
        description: state.embedStudio.desc,
        color: parseInt(state.embedStudio.color.replace('#', ''), 16) || 14753096,
        author: state.embedStudio.author ? { name: state.embedStudio.author, icon_url: state.embedStudio.authorIcon } : undefined,
        fields: (state.embedStudio.fields || []).map(f => ({ name: f.name, value: f.val, inline: f.inline })),
        footer: state.embedStudio.footer ? { text: state.embedStudio.footer } : undefined,
        thumbnail: state.embedStudio.thumbnail ? { url: state.embedStudio.thumbnail } : undefined,
        image: state.embedStudio.image ? { url: state.embedStudio.image } : undefined
      }
    }, null, 2);
    navigator.clipboard?.writeText(jsonStr).then(() => {
      toast('Copied Embed JSON payload to clipboard! 📋');
    }).catch(() => toast('Copied Embed JSON!'));
  });

  document.querySelector('#studio-copy-md')?.addEventListener('click', () => {
    let md = `**${state.embedStudio.title}**\n${state.embedStudio.desc}\n\n`;
    (state.embedStudio.fields || []).forEach(f => {
      md += `• **${f.name}:** ${f.val}\n`;
    });
    if (state.embedStudio.footer) md += `\n*${state.embedStudio.footer}*`;
    navigator.clipboard?.writeText(md).then(() => {
      toast('Copied Discord Markdown to clipboard! ✨');
    }).catch(() => toast('Copied Markdown!'));
  });

  document.querySelector('#mobile-dock-login')?.addEventListener('click', () => showServerSelector());

  // 3D Card Tilt Mouse Dynamics
  init3DTiltEffects();

  // Copy command handler
  document.querySelector('#copy-cmd-btn')?.addEventListener('click', () => {
    const cmdText = `!${state.activeCmd}`;
    navigator.clipboard?.writeText(cmdText).then(() => {
      toast(`Copied ${cmdText} to clipboard!`);
    }).catch(() => {
      toast(`Copied ${cmdText}`);
    });
  });

  // FAQ Accordion Toggle Handlers
  document.querySelectorAll('.faq-question').forEach(q => {
    q.addEventListener('click', () => {
      const item = q.parentElement;
      item.classList.toggle('active');
    });
  });
}

function init3DTiltEffects() {
  // 1. 3D Card Tilt Mouse Dynamics & Glass Spotlight (Excluding interactive UI simulator)
  const elements = document.querySelectorAll('.feat-card, .stat-item, .terminal-box, .audio-showcase, .faq-item, .cta-banner');
  elements.forEach(el => {
    el.addEventListener('mousemove', (e) => {
      const rect = el.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      const centerX = rect.width / 2;
      const centerY = rect.height / 2;
      const rotateX = ((y - centerY) / centerY) * -4.5;
      const rotateY = ((x - centerX) / centerX) * 4.5;

      el.style.setProperty('--mouse-x', `${x}px`);
      el.style.setProperty('--mouse-y', `${y}px`);
      el.style.transform = `perspective(1000px) rotateX(${rotateX.toFixed(2)}deg) rotateY(${rotateY.toFixed(2)}deg) scale3d(1.02, 1.02, 1.02)`;
    });

    el.addEventListener('mouseleave', () => {
      el.style.transform = 'perspective(1000px) rotateX(0deg) rotateY(0deg) scale3d(1, 1, 1)';
    });
  });

  // 2. 3D Scroll Reveal Observer
  const revealElements = document.querySelectorAll('.reveal-3d');
  if ('IntersectionObserver' in window) {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('active');
        }
      });
    }, { threshold: 0.12, rootMargin: '0px 0px -40px 0px' });

    revealElements.forEach(el => observer.observe(el));
  } else {
    revealElements.forEach(el => el.classList.add('active'));
  }

  // 3. Smooth Ambient Parallax on Scroll
  const orbRuby = document.querySelector('#orb-ruby');
  const orbGold = document.querySelector('#orb-gold');
  window.addEventListener('scroll', () => {
    const scrollY = window.scrollY;
    if (orbRuby) {
      orbRuby.style.transform = `translate(-50%, ${scrollY * 0.18}px)`;
    }
    if (orbGold) {
      orbGold.style.transform = `translateY(-${scrollY * 0.12}px)`;
    }
  }, { passive: true });
}

function getChannelTitle() {
  if (state.simChannel === 'music') return 'now-playing';
  if (state.simChannel === 'antinuke') return 'anti-nuke';
  if (state.simChannel === 'tickets') return 'create-ticket';
  if (state.simChannel === 'ai') return 'helix-ai-chat';
  if (state.simChannel === 'logs') return 'audit-log';
  return state.simChannel;
}

function getChannelDesc() {
  if (state.simChannel === 'music') return '24/7 lossless music playback';
  if (state.simChannel === 'antinuke') return 'Zero-tolerance server defense monitor';
  if (state.simChannel === 'tickets') return 'Open a private staff support session';
  if (state.simChannel === 'ai') return 'Context-aware server assistant';
  if (state.simChannel === 'logs') return 'Live 10-channel audit logging stream';
  return 'Private support channel';
}

// ----------------------------------------------------
// SIMULATED DISCORD CHAT CONTENT RENDERER
// ----------------------------------------------------
function renderSimChatContent() {
  const currentTrack = tracks[state.musicTrackIdx] || tracks[0];

  // 1. MUSIC CHANNEL
  if (state.simChannel === 'music') {
    return `
      <div class="d-msg">
        <div class="d-avatar">✦</div>
        <div class="d-msg-body">
          <div class="d-msg-header">
            <span class="d-author">Helix</span>
            <span class="d-bot-badge">BOT ✓</span>
            <span class="d-timestamp">Today at 3:30 AM</span>
          </div>

          <div class="d-embed good">
            <div class="d-embed-author">🟢 NOW PLAYING · 24/7 LOSSLESS</div>
            <div class="d-embed-title">${esc(currentTrack.title)}</div>
            <div class="d-embed-desc">Artist: <b>${esc(currentTrack.artist)}</b> · Requested by <span style="color:var(--brand);font-weight:600;">@Sam</span></div>
            
            <div style="width:100%;height:6px;background:var(--d-input);border-radius:10px;margin-bottom:14px;overflow:hidden;">
              <div style="width:${currentTrack.progress};height:100%;background:linear-gradient(90deg,#7289da,#5865f2);border-radius:10px;"></div>
            </div>

            <div class="d-embed-fields">
              <div class="d-embed-field"><b>Duration</b><span>1:42 / ${currentTrack.duration}</span></div>
              <div class="d-embed-field"><b>Channel</b><span>#general-voice</span></div>
              <div class="d-embed-field"><b>Volume</b><span>${state.musicVol}%</span></div>
              <div class="d-embed-field"><b>Radio Mode</b><span>24/7 ACTIVE</span></div>
            </div>

            <div class="d-action-row">
              <button class="d-btn d-btn-primary" id="sim-music-play">${state.isPlaying ? '⏸ Pause' : '▶ Play'}</button>
              <button class="d-btn d-btn-secondary" id="sim-music-next">⏭ Skip</button>
              <button class="d-btn d-btn-secondary" id="sim-music-shuffle">🔀 Shuffle</button>
              <button class="d-btn d-btn-secondary" id="sim-music-loop">🔁 Loop</button>
            </div>
          </div>

          <div style="display:flex;align-items:center;justify-content:center;height:70px;background:var(--d-embed);border-radius:6px;gap:5px;padding:10px;margin-top:10px;max-width:600px;">
            ${[10, 22, 34, 14, 38, 26, 18, 36, 20, 30, 12, 28, 32, 16, 24, 36, 18].map((h, i) => `
              <div style="width:6px;height:${state.isPlaying ? h : 4}px;background:var(--brand);border-radius:3px;${state.isPlaying ? `animation:eqBounce 1.${(i % 6) + 1}s infinite ease-in-out;` : ''}"></div>
            `).join('')}
          </div>
        </div>
      </div>
    `;
  }

  // 2. ANTI-NUKE CHANNEL
  if (state.simChannel === 'antinuke') {
    return `
      <div class="d-msg">
        <div class="d-avatar red">🛡️</div>
        <div class="d-msg-body">
          <div class="d-msg-header">
            <span class="d-author">Helix Anti-Nuke Sentinel</span>
            <span class="d-bot-badge" style="background:var(--danger)">SHIELD</span>
            <span class="d-timestamp">Live Security Room</span>
          </div>

          <div class="d-embed danger">
            <div class="d-embed-title">🛡️ Zero-Tolerance Server Defense Matrix</div>
            <div class="d-embed-desc">Real-time permission surveillance actively monitoring destructive admin abuse, mass-bans, and channel deletions.</div>
            
            <div class="d-embed-fields">
              <div class="d-embed-field"><b>Shield Status</b><span style="color:var(--good)">ARMED 🟢</span></div>
              <div class="d-embed-field"><b>Strict Mode</b><span style="color:var(--good)">ENABLED (1-Action) 🟢</span></div>
              <div class="d-embed-field"><b>Auto-Recovery</b><span style="color:var(--good)">ACTIVE 🟢</span></div>
              <div class="d-embed-field"><b>Punishment</b><span style="color:var(--danger)">INSTANT BAN ⚖️</span></div>
            </div>

            <div class="d-action-row">
              <button class="d-btn d-btn-danger" id="sim-trigger-attack">🚨 Simulate Rogue Admin Attack</button>
              <button class="d-btn d-btn-secondary" id="sim-reset-defense">🔄 Reset Threat Log</button>
            </div>
          </div>

          <div style="background:var(--d-embed);border-radius:6px;padding:12px;font-family:'Fira Code',monospace;font-size:11.5px;margin-top:10px;max-width:600px;" id="sim-attack-log">
            <div style="color:var(--good);">[03:32:01] Strict Defense: Surveillance Active (0 Threats Detected)</div>
            <div style="color:var(--d-muted);margin-top:4px;">Click "Simulate Rogue Admin Attack" to test 0.04s threat neutralization.</div>
          </div>
        </div>
      </div>
    `;
  }

  // 3. TICKET SYSTEM CHANNEL
  if (state.simChannel === 'tickets') {
    return `
      <div class="d-msg">
        <div class="d-avatar">🎫</div>
        <div class="d-msg-body">
          <div class="d-msg-header">
            <span class="d-author">Helix Ticket System</span>
            <span class="d-bot-badge">BOT ✓</span>
            <span class="d-timestamp">Today at 3:35 AM</span>
          </div>

          <div class="d-embed">
            <div class="d-embed-author">🎫 HELIX AUTOMATED SUPPORT CENTER</div>
            <div class="d-embed-title">Need Help? Open a Staff Ticket</div>
            <div class="d-embed-desc">
              Welcome to the support center! Select a category from the dropdown menu below or click **Open Ticket** to create a private channel with our staff team.
            </div>

            <div class="d-embed-fields">
              <div class="d-embed-field"><b>Average Response</b><span>&lt; 2 Minutes</span></div>
              <div class="d-embed-field"><b>Staff On Duty</b><span>@Support Team (Online)</span></div>
              <div class="d-embed-field"><b>Transcripts</b><span>Automated HTML Log</span></div>
              <div class="d-embed-field"><b>Privacy</b><span>Encrypted & Private</span></div>
            </div>

            <div class="d-select-wrap">
              <select class="d-select" id="sim-ticket-select">
                <option value="">Select a Support Category...</option>
                <option value="tech">🛠️ Technical Support — Command errors or bot configuration</option>
                <option value="billing">💳 Billing & Premium — Server upgrades and tier donations</option>
                <option value="partnership">🤝 Server Partnership — Cross-server events & affiliation</option>
                <option value="report">📢 Member Report — Report a rule-breaker or toxic user</option>
              </select>
            </div>

            <div class="d-action-row" style="margin-top:12px;">
              <button class="d-btn d-btn-primary" id="sim-open-ticket-btn">🎫 Open Ticket</button>
              <button class="d-btn d-btn-secondary" id="sim-my-tickets-btn">📜 My Active Tickets (${state.simTickets.length})</button>
            </div>

            <div class="d-embed-footer">
              <span>✦ Helix Ticket Builder Engine · One-Click Deploy</span>
            </div>
          </div>
        </div>
      </div>
    `;
  }

  // 4. AI CHAT CHANNEL
  if (state.simChannel === 'ai') {
    return `
      ${state.simAiMessages.map(m => `
        <div class="d-msg">
          <div class="d-avatar" style="${m.isBot ? '' : 'background:#248046;'}">${m.isBot ? '🤖' : 'U'}</div>
          <div class="d-msg-body">
            <div class="d-msg-header">
              <span class="d-author">${esc(m.sender)}</span>
              ${m.isBot ? `<span class="d-bot-badge">${esc(m.botBadge || 'BOT ✓')}</span>` : ''}
              <span class="d-timestamp">${m.time}</span>
            </div>

            ${m.text ? `<div class="d-text-content">${esc(m.text)}</div>` : ''}

            ${m.embed ? `
              <div class="d-embed">
                <div class="d-embed-title">${esc(m.embed.title)}</div>
                <div class="d-embed-desc">${esc(m.embed.desc)}</div>
                ${m.embed.fields ? `
                  <div class="d-embed-fields">
                    ${m.embed.fields.map(f => `
                      <div class="d-embed-field"><b>${esc(f.name)}</b><span>${esc(f.val)}</span></div>
                    `).join('')}
                  </div>
                ` : ''}
              </div>
            ` : ''}
          </div>
        </div>
      `).join('')}

      <div style="background:var(--d-embed);border-radius:8px;padding:12px 14px;max-width:600px;margin-top:8px;">
        <div style="font-size:11px;font-weight:700;color:var(--d-muted);margin-bottom:8px;">QUICK PROMPT SUGGESTIONS:</div>
        <div class="d-action-row" style="margin-top:0;">
          <button class="d-btn d-btn-secondary sim-ai-prompt-btn" data-q="What is Anti-Nuke strict mode?">"What is Anti-Nuke strict mode?"</button>
          <button class="d-btn d-btn-secondary sim-ai-prompt-btn" data-q="How do I setup 10-channel logging?">"How do I setup 10-channel logging?"</button>
          <button class="d-btn d-btn-secondary sim-ai-prompt-btn" data-q="How do I customize the ticket builder?">"How do I customize the ticket builder?"</button>
        </div>
      </div>
    `;
  }

  // 5. AUDIT LOGGING CHANNEL
  if (state.simChannel === 'logs') {
    return `
      <div class="d-msg">
        <div class="d-avatar">📜</div>
        <div class="d-msg-body">
          <div class="d-msg-header">
            <span class="d-author">Helix Audit Logger</span>
            <span class="d-bot-badge">AUDIT</span>
            <span class="d-timestamp">Live Multi-Channel Stream</span>
          </div>

          <div style="display:flex;flex-direction:column;gap:8px;max-width:600px;margin-top:6px;">
            ${state.simLogItems.map(item => `
              <div class="d-embed ${item.color}" style="margin-top:0;padding:10px 14px;">
                <div style="display:flex;align-items:center;justify-content:space-between;">
                  <b style="font-size:11.5px;color:var(--d-header);">${item.event}</b>
                  <span style="font-family:'Fira Code',monospace;font-size:10.5px;color:var(--d-muted);">${item.time}</span>
                </div>
                <div style="font-size:12.5px;color:var(--d-text);margin-top:4px;">${esc(item.desc)}</div>
              </div>
            `).join('')}
          </div>
        </div>
      </div>
    `;
  }

  // 6. DYNAMIC TICKET CHANNEL SESSION
  return `
    <div class="d-msg">
      <div class="d-avatar">🎫</div>
      <div class="d-msg-body">
        <div class="d-msg-header">
          <span class="d-author">Helix Tickets</span>
          <span class="d-bot-badge">TICKET</span>
          <span class="d-timestamp">Just Now</span>
        </div>

        <div class="d-embed good">
          <div class="d-embed-title">🎫 Ticket #${esc(state.simChannel)}</div>
          <div class="d-embed-desc">
            Welcome <span style="color:var(--brand);font-weight:700;">@User</span>! Support staff has been notified of your request. Please state your query in detail.
          </div>

          <div class="d-embed-fields">
            <div class="d-embed-field"><b>Claimed By</b><span id="ticket-claim-status">Unclaimed</span></div>
            <div class="d-embed-field"><b>Category</b><span>Technical Assistance</span></div>
          </div>

          <div class="d-action-row">
            <button class="d-btn d-btn-primary" id="sim-claim-ticket-btn">🔒 Claim Ticket</button>
            <button class="d-btn d-btn-danger" id="sim-close-ticket-btn">📁 Close & Save Transcript</button>
          </div>
        </div>
      </div>
    </div>
  `;
}

function bindSimChannelButtons() {
  document.querySelectorAll('[data-sim-ch]').forEach(btn => {
    btn.onclick = () => {
      state.simChannel = btn.dataset.simCh;
      updateSimView();
    };
  });
}

function updateSimView() {
  // Update sidebar active buttons
  document.querySelectorAll('[data-sim-ch]').forEach(b => {
    b.classList.toggle('active', b.dataset.simCh === state.simChannel);
  });

  // Re-render sidebar ticket list if needed
  const chList = document.querySelector('.discord-sim-ch-list');
  if (chList) {
    chList.innerHTML = `
      <div class="discord-sim-ch-category">
        <span>TEXT CHANNELS</span>
        <span>+</span>
      </div>

      <button class="discord-sim-ch-btn ${state.simChannel === 'music' ? 'active' : ''}" data-sim-ch="music">
        <span class="hash">#</span> 🎵-now-playing
      </button>
      <button class="discord-sim-ch-btn ${state.simChannel === 'antinuke' ? 'active' : ''}" data-sim-ch="antinuke">
        <span class="hash">#</span> 🛡️-anti-nuke
      </button>
      <button class="discord-sim-ch-btn ${state.simChannel === 'tickets' ? 'active' : ''}" data-sim-ch="tickets">
        <span class="hash">#</span> 🎫-create-ticket
      </button>
      <button class="discord-sim-ch-btn ${state.simChannel === 'ai' ? 'active' : ''}" data-sim-ch="ai">
        <span class="hash">#</span> 🤖-helix-ai-chat
      </button>
      <button class="discord-sim-ch-btn ${state.simChannel === 'logs' ? 'active' : ''}" data-sim-ch="logs">
        <span class="hash">#</span> 📜-audit-log
      </button>

      ${state.simTickets.length ? `
        <div class="discord-sim-ch-category" style="margin-top:12px;">
          <span>ACTIVE TICKETS</span>
        </div>
        ${state.simTickets.map(t => `
          <button class="discord-sim-ch-btn ${state.simChannel === t ? 'active' : ''}" data-sim-ch="${t}" style="color:var(--good);">
            <span class="hash">#</span> 🎫-${t}
          </button>
        `).join('')}
      ` : ''}

      <div class="discord-sim-ch-category" style="margin-top:14px;">
        <span>VOICE CHANNELS</span>
      </div>
      <div class="discord-sim-ch-btn" style="color:var(--good);cursor:default;">
        <span>🔊</span> 24/7 Music Lounge
      </div>
    `;
    bindSimChannelButtons();
  }

  // Update topbar
  const topbarTitle = document.querySelector('.discord-sim-ch-topbar-left span:nth-child(2)');
  if (topbarTitle) topbarTitle.textContent = getChannelTitle();
  const topbarDesc = document.querySelector('.discord-sim-ch-topbar-desc');
  if (topbarDesc) topbarDesc.textContent = getChannelDesc();

  // Update input placeholder
  const chatInput = document.querySelector('#sim-chat-input');
  if (chatInput) chatInput.placeholder = `Message #${getChannelTitle()}...`;

  // Update Feed and attach events
  refreshFeed();
}

function attachSimEvents() {
  // Music controls
  document.querySelector('#sim-music-play')?.addEventListener('click', (e) => {
    e.preventDefault();
    state.isPlaying = !state.isPlaying;
    toast(state.isPlaying ? '▶ Music playback resumed' : '⏸ Music playback paused');
    refreshFeed();
  });

  document.querySelector('#sim-music-next')?.addEventListener('click', (e) => {
    e.preventDefault();
    state.musicTrackIdx = (state.musicTrackIdx + 1) % tracks.length;
    const t = tracks[state.musicTrackIdx];
    toast(`⏭ Skipped to: ${t.title}`);
    refreshFeed();
  });

  document.querySelector('#sim-music-shuffle')?.addEventListener('click', (e) => {
    e.preventDefault();
    state.musicTrackIdx = Math.floor(Math.random() * tracks.length);
    const t = tracks[state.musicTrackIdx];
    toast(`🔀 Queue Shuffled! Now playing: ${t.title}`);
    refreshFeed();
  });

  document.querySelector('#sim-music-loop')?.addEventListener('click', (e) => {
    e.preventDefault();
    toast('🔁 Loop Mode toggled for current track');
  });

  // Anti-Nuke trigger
  document.querySelector('#sim-trigger-attack')?.addEventListener('click', (e) => {
    e.preventDefault();
    const logEl = document.querySelector('#sim-attack-log');
    if (!logEl) return;
    logEl.innerHTML = `
      <div style="color:var(--danger);font-weight:700;">[03:36:10] 🚨 Rogue Admin deleted channel #general-chat</div>
      <div style="color:var(--warning);">[03:36:10] Helix Zero-Tolerance Intercept Triggered (0.04s)</div>
      <div style="color:var(--good);font-weight:700;">[03:36:10] ✓ Banned Rogue Admin & Revoked Roles</div>
      <div style="color:var(--brand);font-weight:700;">[03:36:11] ✓ Channel #general-chat AUTO-RESTORED with all permissions!</div>
    `;
    toast('🛡️ Threat Intercepted: Rogue Admin Banned & Channel Restored!');
  });

  document.querySelector('#sim-reset-defense')?.addEventListener('click', (e) => {
    e.preventDefault();
    const logEl = document.querySelector('#sim-attack-log');
    if (!logEl) return;
    logEl.innerHTML = `<div style="color:var(--good);">[03:36:50] Strict Defense: Surveillance Active (0 Threats Detected)</div>`;
    toast('Threat log reset to surveillance mode.');
  });

  // Ticket create
  document.querySelector('#sim-ticket-select')?.addEventListener('change', (e) => {
    if (e.target.value) {
      createNewTicket();
    }
  });

  document.querySelector('#sim-open-ticket-btn')?.addEventListener('click', (e) => {
    e.preventDefault();
    createNewTicket();
  });

  document.querySelector('#sim-my-tickets-btn')?.addEventListener('click', (e) => {
    e.preventDefault();
    if (state.simTickets.length) {
      state.simChannel = state.simTickets[0];
      updateSimView();
    } else {
      toast('No active tickets. Select a category to open one!');
    }
  });

  // Ticket session controls
  document.querySelector('#sim-claim-ticket-btn')?.addEventListener('click', (e) => {
    e.preventDefault();
    const status = document.querySelector('#ticket-claim-status');
    if (status) status.innerHTML = '<span style="color:var(--good);font-weight:700;">Claimed by @OreoMod (Renamed to #oreo-15007)</span>';
    toast('Ticket claimed & channel renamed to #oreo-15007');
  });

  document.querySelector('#sim-close-ticket-btn')?.addEventListener('click', (e) => {
    e.preventDefault();
    toast('Ticket closed & HTML transcript saved to #ticket-transcripts');
    state.simTickets = state.simTickets.filter(t => t !== state.simChannel);
    state.simChannel = 'tickets';
    updateSimView();
  });

  // AI Prompt buttons
  document.querySelectorAll('.sim-ai-prompt-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      sendAiMessage(btn.dataset.q);
    });
  });
}

function createNewTicket() {
  const num = String(state.simTickets.length + 1).padStart(4, '0');
  const tName = `ticket-${num}`;
  if (!state.simTickets.includes(tName)) {
    state.simTickets.push(tName);
  }
  state.simChannel = tName;
  toast(`Created ticket channel: #${tName}`);
  updateSimView();
}

function handleSimUserMessage(text) {
  if (state.simChannel === 'ai') {
    sendAiMessage(text);
    return;
  }

  // Handle in other channels
  if (state.simChannel === 'music') {
    if (text.startsWith('!play') || text.startsWith('play')) {
      const q = text.replace(/^!play\s*/i, '').replace(/^play\s*/i, '') || 'Lofi Beats';
      state.musicTrackIdx = (state.musicTrackIdx + 1) % tracks.length;
      tracks[state.musicTrackIdx].title = q.length > 3 ? q : tracks[state.musicTrackIdx].title;
      state.isPlaying = true;
      toast(`🎵 Added to queue: ${q}`);
      refreshFeed();
      return;
    } else if (text.startsWith('!skip') || text === 'skip') {
      state.musicTrackIdx = (state.musicTrackIdx + 1) % tracks.length;
      toast(`⏭ Skipped track.`);
      refreshFeed();
      return;
    }
  }

  toast(`Sent in #${getChannelTitle()}: "${text}"`);
}

function sendAiMessage(query) {
  state.simAiMessages.push({
    sender: 'You',
    isBot: false,
    time: 'Just Now',
    text: query
  });

  let botReply = '';
  if (query.includes('Anti-Nuke') || query.includes('anti-nuke')) {
    botReply = 'Strict Mode automatically bans rogue admins on their very first unauthorized channel or role deletion (0.04s execution) and immediately recreates the deleted channel with identical permissions and topics!';
  } else if (query.includes('10-channel') || query.includes('logging')) {
    botReply = 'Run `!setup_logs` in Discord or select target channels in the Helix Web Dashboard to automatically bind all 10 specialized log channels (messages, joins/leaves, roles, voice, bans, and channel creates/deletes).';
  } else if (query.includes('ticket')) {
    botReply = 'Run `!ticket builder` in Discord to launch the visual panel builder! You can customize embed titles, colors, banners, and add/edit/delete category select options in real time.';
  } else if (query.includes('snipe')) {
    botReply = 'Use `!snipe` (or `!s`) to recover recently deleted messages with attached images, stickers, and timestamps, `!editsnipe` to view before/after edit diffs, or `!clearsnipe` to clear history!';
  } else {
    botReply = `Thanks for asking! Helix provides studio-quality 24/7 music, zero-tolerance anti-nuke, embed ticket builders, leveling, and web controls to power your community.`;
  }

  state.simAiMessages.push({
    sender: 'Helix AI',
    isBot: true,
    botBadge: 'GEMINI PRO',
    time: 'Just Now',
    embed: {
      title: '✦ Helix AI Response',
      desc: botReply
    }
  });

  refreshFeed();
}

function refreshFeed() {
  const feed = document.querySelector('#sim-chat-feed');
  if (feed) feed.innerHTML = renderSimChatContent();
  attachSimEvents();
  feed?.scrollTo({ top: feed.scrollHeight, behavior: 'smooth' });
}

function renderCommandPreview(cmd) {
  if (cmd === 'play') {
    return `<div style="color:var(--muted)">$ user: <b>!play lofi beats</b></div>
<div style="color:var(--good);margin-top:8px;">✦ Helix: Added to queue: <b>Lofi Cyber Chill Beats (3:42)</b></div>
<div style="color:var(--brand)">🎵 Now Playing in Voice Channel: <b>#general-voice</b> (Lossless 24/7)</div>`;
  } else if (cmd === 'ticket builder') {
    return `<div style="color:var(--muted)">$ admin: <b>/ticket builder</b></div>
<div style="color:var(--brand);margin-top:8px;">🎫 [Helix Visual Ticket Panel Builder]</div>
<div style="color:#fff;">• Title: Support Center | Color: #5865F2 | Categories: 4 Configured</div>
<div style="color:var(--good);">🚀 Status: Ready to deploy into #support-tickets channel.</div>`;
  } else if (cmd === 'snipe') {
    return `<div style="color:var(--muted)">$ user: <b>!snipe</b></div>
<div style="color:var(--brand);margin-top:8px;">🎯 <b>Snipe • #general</b> (Deleted 12s ago)</div>
<div style="color:#fff;">• Author: <b>@GhostUser</b> | Attachments: <code>1 image</code></div>
<div style="color:var(--muted);">"Did anyone see what I just typed??"</div>
<div style="color:var(--good);margin-top:4px;">✦ Interactive controls: [◀ Prev] [1/5] [Next ▶] [🗑️ Clear Cache]</div>`;
  } else if (cmd === 'autorole add @Members') {
    return `<div style="color:var(--muted)">$ admin: <b>!autorole add @Members</b></div>
<div style="color:var(--good);margin-top:8px;">👥 Auto Role Added: <b>@Members</b> will now be granted to new humans on join.</div>
<div style="color:var(--brand);">Tip: Use <b>!autorole bot @Bots</b> to configure automated bot roles.</div>`;
  } else if (cmd === 'setwelcome #welcome') {
    return `<div style="color:var(--muted)">$ admin: <b>!setwelcome #welcome</b></div>
<div style="color:var(--good);margin-top:8px;">👋 Welcome announcements active in <b>#welcome</b></div>
<div style="color:#fff;">• Mode: <b>Canvas PNG Card</b> | Placeholder: <b>{user} (#{membercount})</b></div>`;
  } else if (cmd === 'setstarboard #starboard') {
    return `<div style="color:var(--muted)">$ admin: <b>!setstarboard #starboard</b></div>
<div style="color:var(--good);margin-top:8px;">⭐ Starboard showcase channel designated: <b>#starboard</b></div>
<div style="color:#fff;">• Threshold: <b>3 ⭐ reactions</b> | Auto-pins top community messages.</div>`;
  } else if (cmd === 'stats') {
    return `<div style="color:var(--muted)">$ user: <b>!stats</b></div>
<div style="color:var(--brand);margin-top:8px;">📊 Helix Platform Scale & Telemetry:</div>
<div style="color:#fff;">• Scale: <b>10,000+ Communities</b> | Latency: <b>18.2ms</b> | Status: <b>🟢 Operational</b></div>`;
  } else if (cmd === 'antinuke strict on') {
    return `<div style="color:var(--muted)">$ owner: <b>!antinuke strict on</b></div>
<div style="color:var(--danger);margin-top:8px;">🛡️ Anti-Nuke Strict Mode: <b>ENABLED (1-Action Zero Tolerance)</b></div>
<div style="color:var(--good);">Auto-Recovery: ACTIVE (Auto-restores deleted channels & roles)</div>`;
  } else if (cmd === 'setlog') {
    return `<div style="color:var(--muted)">$ admin: <b>!setlog message_delete #audit-logs</b></div>
<div style="color:var(--good);margin-top:8px;">✓ Successfully bound event <b>message_delete</b> to <b>#audit-logs</b>.</div>
<div style="color:var(--muted)">Tip: Use !setup_logs to automatically create all 10 specialized log channels.</div>`;
  } else if (cmd === 'rank') {
    return `<div style="color:var(--muted)">$ user: <b>!rank</b></div>
<div style="color:var(--brand);margin-top:8px;">📈 Level 42 · Rank #1 in Server</div>
<div style="color:#fff;">XP: 14,850 / 15,200 (97.7%) · Awarded Role: <b>@Elite VIP</b></div>`;
  } else {
    return `<div style="color:var(--muted)">$ user: <b>!ask What is Helix?</b></div>
<div style="color:var(--brand);margin-top:8px;">🤖 Helix AI:</div>
<div style="color:var(--ink);">Helix is a next-generation Discord multi-purpose bot featuring studio-quality music, impenetrable Anti-Nuke defense, modular logging, embed ticket builders, leveling, and web controls!</div>`;
  }
}

// ====================================================
// 2. SERVER SELECTION HUB
// ====================================================
function renderServerSelectionHub() {
  const filtered = state.guilds.filter(g => (g.name || '').toLowerCase().includes((state.searchQuery || '').toLowerCase()));
  const currentTheme = getStoredTheme();

  app.className = 'shell no-sidebar';
  app.innerHTML = `
    <main style="width:100%;margin-left:0;">
      <header class="topbar">
        <div class="landing-brand" id="hub-brand-home">
          <span>✦</span>
          <b>helix</b>
        </div>
        <div class="crumb" style="font-size:13px;font-weight:700;">
          Select a Server
        </div>
        <div class="profile" id="hub-profile">
          ${state.me?.user ? `
            ${iconUrl(state.me.user.id, state.me.user.avatar) ? `<img src="${iconUrl(state.me.user.id, state.me.user.avatar)}" alt="">` : `<span class="initials">${esc(state.me.user.username?.[0] || 'U')}</span>`}
            <span>${esc(state.me.user.username || 'User')}</span>
            <button class="logout" id="logout">Sign out</button>
          ` : ''}
        </div>
      </header>

      <div class="server-hub">
        <div class="server-hub-head">
          <h1>Select a Server to Configure</h1>
          <p>Choose a Discord server where you have Manage Server or Administrator permissions.</p>
          <div class="server-search-wrap">
            <span class="search-icon">🔍</span>
            <input type="text" id="server-search" placeholder="Search servers..." value="${esc(state.searchQuery)}">
          </div>
        </div>
        <div class="server-grid">
          ${filtered.length ? filtered.map(g => `
            <div class="server-card" data-select-guild="${g.id}">
              <div class="server-card-top">
                <div class="server-card-icon">${avatar(g)}</div>
                <div class="server-card-info">
                  <h3>${esc(g.name)}</h3>
                  <p>${Number(g.member_count || 0).toLocaleString()} members</p>
                </div>
              </div>
              <div class="server-card-badges">
                <span class="pill green">✦ HELIX ACTIVE</span>
                ${g.owner ? '<span class="pill">OWNER</span>' : '<span class="pill">ADMIN</span>'}
              </div>
              <button class="server-card-btn">Configure Server ➔</button>
            </div>
          `).join('') : `
            <div class="empty-state" style="grid-column: 1 / -1;">
              <strong>No servers found</strong>
              ${state.searchQuery ? 'Try adjusting your search query.' : 'No manageable servers with Helix found.'}
            </div>
          `}
        </div>
      </div>
    </main>
  `;

  document.querySelector('#hub-brand-home')?.addEventListener('click', () => showLanding());
  document.querySelector('#logout')?.addEventListener('click', async () => { await api('/auth/logout', { method: 'POST' }); location.reload(); });
  document.querySelector('#theme-toggle')?.addEventListener('click', () => {
    const next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    setTheme(next);
  });

  document.querySelector('#server-search')?.addEventListener('input', (e) => {
    state.searchQuery = e.target.value;
    renderServerSelectionHub();
    const input = document.querySelector('#server-search');
    if (input) {
      input.focus();
      input.setSelectionRange(state.searchQuery.length, state.searchQuery.length);
    }
  });

  document.querySelectorAll('[data-select-guild]').forEach(card => {
    card.addEventListener('click', () => {
      const g = state.guilds.find(x => x.id === card.dataset.selectGuild);
      if (g) selectServer(g);
    });
  });
}

// ====================================================
// 3. CATEGORIZED SERVER CONTROL CENTER & DASHBOARD SHELL
// ====================================================
function renderDashboardShell() {
  const currentTheme = getStoredTheme();
  app.className = 'shell';
  app.innerHTML = `
    <aside class="sidebar">
      <div class="brand" id="side-brand">
        <span>✦</span>
        <b>helix</b>
      </div>
      <div class="guild-list" id="guild-list">
        <div class="active-server-card">
          <div class="server-icon-wrap">${avatar(state.selected)}</div>
          <div class="server-meta">
            <b>${esc(state.selected?.name || '')}</b>
            <small>${Number(state.selected?.member_count || 0).toLocaleString()} members</small>
          </div>
          <button class="switch-btn" id="sidebar-switch-btn" title="Switch server">⇄ Switch</button>
        </div>
      </div>
      
      <nav id="navigation" aria-label="Dashboard navigation">
        <p class="nav-label"><span>OVERVIEW & ANALYTICS</span></p>
        <button class="nav-button ${state.page === 'overview' ? 'active' : ''}" data-page="overview">
          <i>⌘</i> Overview <span class="nav-badge">LIVE</span>
        </button>

        <p class="nav-label"><span>SECURITY & SENTINEL</span></p>
        <button class="nav-button ${state.page === 'automod' ? 'active' : ''}" data-page="automod">
          <i>🤖</i> AutoMod Defense <span class="nav-badge">AUTO</span>
        </button>
        <button class="nav-button ${state.page === 'antinuke' ? 'active' : ''}" data-page="antinuke">
          <i>🏰</i> Anti-Nuke Suite <span class="nav-badge" style="color:var(--danger)">ARMED</span>
        </button>
        <button class="nav-button ${state.page === 'activity' ? 'active' : ''}" data-page="activity">
          <i>◷</i> Moderation Log
        </button>

        <p class="nav-label"><span>COMMUNITY & REWARDS</span></p>
        <button class="nav-button ${state.page === 'community' ? 'active' : ''}" data-page="community">
          <i>👥</i> Auto Roles & Welcome <span class="nav-badge" style="color:var(--good)">NEW</span>
        </button>
        <button class="nav-button ${state.page === 'tickets' ? 'active' : ''}" data-page="tickets">
          <i>🎫</i> Ticket System <span class="nav-badge" style="color:var(--good)">LIVE</span>
        </button>
        <button class="nav-button ${state.page === 'leveling' ? 'active' : ''}" data-page="leveling">
          <i>📈</i> Leveling & XP
        </button>
        <button class="nav-button ${state.page === 'giveaways' ? 'active' : ''}" data-page="giveaways">
          <i>🎉</i> Giveaways
        </button>
        <button class="nav-button ${state.page === 'economy' ? 'active' : ''}" data-page="economy">
          <i>💰</i> Economy & Shop
        </button>
        <button class="nav-button ${state.page === 'vanity' ? 'active' : ''}" data-page="vanity">
          <i>📡</i> Vanity Tracker
        </button>

        <p class="nav-label"><span>CORE & ROUTING</span></p>
        <button class="nav-button ${state.page === 'general' ? 'active' : ''}" data-page="general">
          <i>⚙</i> General & AI
        </button>
        <button class="nav-button ${state.page === 'logging' ? 'active' : ''}" data-page="logging">
          <i>📜</i> Action Logging <span class="nav-badge">10 CH</span>
        </button>
      </nav>

      <div class="sidebar-foot">
        <span class="status-dot"></span> Bot dashboard
      </div>
    </aside>

    <main>
      <header class="topbar">
        <button id="menu" class="menu" aria-label="Open navigation">☰</button>
        <div id="crumb" class="crumb"></div>
        <div class="profile" id="profile">
          ${state.me?.user ? `
            ${iconUrl(state.me.user.id, state.me.user.avatar) ? `<img src="${iconUrl(state.me.user.id, state.me.user.avatar)}" alt="">` : `<span class="initials">${esc(state.me.user.username?.[0] || 'U')}</span>`}
            <span>${esc(state.me.user.username || 'User')}</span>
            <button class="logout" id="logout">Sign out</button>
          ` : ''}
        </div>
      </header>
      <div id="content"></div>

      <!-- FLOATING UNSAVED CHANGES BAR -->
      <div class="unsaved-bar" id="unsaved-bar">
        <span>⚠️ You have unsaved changes in this module</span>
        <div style="display:flex;gap:10px;">
          <button class="button secondary" id="discard-bar-btn" style="padding:6px 14px;font-size:12px;">Discard</button>
          <button class="button" id="save-bar-btn" style="padding:6px 16px;font-size:12px;">Save Changes ➔</button>
        </div>
      </div>
    </main>
  `;

  // Attach Dashboard Shell Listeners
  document.querySelector('#side-brand')?.addEventListener('click', () => showLanding());
  document.querySelector('#sidebar-switch-btn')?.addEventListener('click', () => showServerSelector());
  document.querySelector('#logout')?.addEventListener('click', async () => { await api('/auth/logout', { method: 'POST' }); location.reload(); });
  document.querySelector('#theme-toggle')?.addEventListener('click', () => {
    const next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    setTheme(next);
  });
  document.querySelector('#menu')?.addEventListener('click', () => document.querySelector('.sidebar')?.classList.toggle('open'));

  document.querySelector('#save-bar-btn')?.addEventListener('click', () => saveSettings());
  document.querySelector('#discard-bar-btn')?.addEventListener('click', () => {
    clearUnsaved();
    renderServerModulePage();
  });

  const nav = document.querySelector('#navigation');
  nav?.querySelectorAll('[data-page]').forEach(b => b.addEventListener('click', () => {
    state.page = b.dataset.page;
    nav.querySelectorAll('[data-page]').forEach(n => n.classList.toggle('active', n.dataset.page === state.page));
    renderServerModulePage();
    document.querySelector('.sidebar')?.classList.remove('open');
  }));

  renderServerModulePage();
}

function title(titleText, subtitle, action = '') {
  const crumb = document.querySelector('#crumb');
  if (crumb) {
    crumb.innerHTML = `<a id="crumb-servers" style="cursor:pointer;color:var(--brand)">Servers</a> <span style="margin:0 4px;color:var(--muted)">/</span> <span>${esc(state.selected?.name || '')}</span> <span style="margin:0 4px;color:var(--muted)">/</span> <span style="color:var(--ink)">${titleText}</span>`;
    document.querySelector('#crumb-servers')?.addEventListener('click', (e) => { e.preventDefault(); showServerSelector(); });
  }
  return `<div class="title-row"><div><div class="eyebrow"><i></i> HELIX CONTROL ENGINE</div><h1>${titleText}</h1><p>${subtitle}</p></div>${action}</div>`;
}

// ----------------------------------------------------
// SERVER MODULE PAGES (ENHANCED WITH UI/UX PRO MAX)
// ----------------------------------------------------
async function renderServerModulePage() {
  const content = document.querySelector('#content');
  if (!content) return;
  content.innerHTML = `<div class="empty-state"><strong>Loading ${esc(state.selected?.name || 'Server')}</strong>Fetching live data from Helix…</div>`;

  try {
    if (state.page === 'overview') return await overview();
    if (state.page === 'community') return await communityManager();
    if (state.page === 'general') return await generalSettings();
    if (state.page === 'logging') return await loggingSettings();
    if (state.page === 'automod') return await automodSettings();
    if (state.page === 'antinuke') return await antinukeSettings();
    if (state.page === 'tickets') return await ticketsManager();
    if (state.page === 'leveling') return await levelingSettings();
    if (state.page === 'giveaways') return await giveawaysManager();
    if (state.page === 'economy') return await economyManager();
    if (state.page === 'vanity') return await vanityManager();
    return await activityLog();
  } catch (error) {
    content.innerHTML = `<div class="empty-state"><strong>Couldn’t load this section</strong>${esc(error.message)}</div>`;
  }
}

// Module 1: OVERVIEW
async function overview() {
  const content = document.querySelector('#content');
  const d = await api(`/api/guilds/${state.selected.id}/overview`);
  const a = d.analytics || {};
  const values = [Math.max(5, a.msg_1d || 0), Math.max(5, Math.round((a.msg_7d || 0) / 7)), Math.max(5, a.msg_30d || 0), Math.max(5, (a.vc_1d_hrs || 0) * 10), Math.max(5, (a.vc_7d_hrs || 0) * 2), Math.max(5, a.msg_7d || 0), Math.max(5, (a.msg_1d || 0) * 2)];
  const max = Math.max(...values, 10);
  const topList = a.top_channels || [];

  content.innerHTML = `
    <div class="content">
      ${title('Community Operations Center', 'Real-time telemetry, server activity index, and moderation statistics.')}
      
      <section class="metrics">
        <article class="metric">
          <div class="metric-top">TOTAL MEMBERS <span class="pill">GUILD</span></div>
          <strong>${Number(d.metrics?.members || 0).toLocaleString()}</strong>
          <div class="metric-foot">
            <span>Verified accounts</span>
            <span class="metric-trend up">▲ Active</span>
          </div>
        </article>

        <article class="metric">
          <div class="metric-top">MESSAGES TODAY <span class="pill green">24H</span></div>
          <strong>${Number(d.metrics?.messages_today || 0).toLocaleString()}</strong>
          <div class="metric-foot">
            <span>Analytics tracked</span>
            <span class="metric-trend up">▲ Live</span>
          </div>
        </article>

        <article class="metric">
          <div class="metric-top">MOD ACTIONS TODAY <span class="pill danger">SECURITY</span></div>
          <strong>${Number(d.metrics?.mod_actions_today || 0).toLocaleString()}</strong>
          <div class="metric-foot">
            <span>Threats neutralized</span>
            <span class="metric-trend neutral">● 0.04s</span>
          </div>
        </article>

        <article class="metric">
          <div class="metric-top">ACTIVE TICKETS <span class="pill">SUPPORT</span></div>
          <strong>${Number(d.metrics?.open_tickets || 0).toLocaleString()}</strong>
          <div class="metric-foot">
            <span>Pending response</span>
            <span class="metric-trend up">✓ Ready</span>
          </div>
        </article>
      </section>

      <section class="grid">
        <article class="card">
          <div class="card-head">
            <div><h2>Voice & Activity Distribution</h2><p>Participation distribution across the last 7 to 30 days</p></div>
            <span class="pill live">LIVE TELEMETRY</span>
          </div>
          <div class="activity-chart">
            ${values.map((v,i) => `<div class="bar" style="height:${Math.max(14, Math.round(v / max * 100))}%" title="Activity Index: ${v}"></div>`).join('')}
          </div>
          <div class="activity-summary">
            <div><b>${Number(a.msg_7d || 0).toLocaleString()}</b><span>Messages · 7d</span></div>
            <div><b>${Number(a.vc_7d_hrs || 0)}h</b><span>Voice Time · 7d</span></div>
            <div><b>${Number(a.msg_30d || 0).toLocaleString()}</b><span>Messages · 30d</span></div>
          </div>
        </article>

        <article class="card">
          <div class="card-head">
            <div><h2>Top Active Channels</h2><p>Highest engagement volume this week</p></div>
          </div>
          <ul class="list">
            ${topList.length ? topList.map((r,i) => `<li><span class="icon ${i === 0 ? 'green' : ''}">#</span><span><b>${esc(channelName(r.channel_id || r[0]))}</b><small>Active conversation stream</small></span><span class="right">${Number(r.total || r[1] || 0).toLocaleString()} msgs</span></li>`).join('') : '<li><span class="subtext">Helix will populate top channels as members chat.</span></li>'}
          </ul>
        </article>
      </section>
    </div>
  `;
}

function channelName(id) {
  const c = state.settings?.channels?.find(x => x.id === String(id));
  return c ? `#${c.name}` : `Channel ${id}`;
}

function channelSelect(d, key, val, help = '') {
  return `
    <div class="field">
      <select data-setting="${key}" onchange="markUnsaved()">
        <option value="">None / Not Configured</option>
        ${(d.channels || []).filter(x => x.type === 'text').map(x => `<option value="${x.id}" ${String(val || '') === x.id ? 'selected' : ''}>#${esc(x.name)}</option>`).join('')}
      </select>
      ${help ? `<span class="subtext">${help}</span>` : ''}
    </div>
  `;
}

function categorySelect(d, key, val, help = '') {
  return `
    <div class="field">
      <select data-setting="${key}" onchange="markUnsaved()">
        <option value="">Default / Root Category</option>
        ${(d.categories || []).map(x => `<option value="${x.id}" ${String(val || '') === x.id ? 'selected' : ''}>📁 ${esc(x.name)}</option>`).join('')}
      </select>
      ${help ? `<span class="subtext">${help}</span>` : ''}
    </div>
  `;
}

function roleSelect(d, key, val, help = '') {
  return `
    <div class="field">
      <select data-setting="${key}" onchange="markUnsaved()">
        <option value="">None / Default Staff</option>
        ${(d.roles || []).map(x => `<option value="${x.id}" ${String(val || '') === x.id ? 'selected' : ''}>@${esc(x.name)}</option>`).join('')}
      </select>
      ${help ? `<span class="subtext">${help}</span>` : ''}
    </div>
  `;
}

function toggleSwitch(key, label, help, checked = false) {
  return `
    <div class="setting-row">
      <div><b>${label}</b><small>${help}</small></div>
      <label class="switch">
        <input type="checkbox" data-setting="${key}" ${checked ? 'checked' : ''} onchange="markUnsaved()">
        <span class="slider"></span>
      </label>
    </div>
  `;
}

// Module 2: GENERAL & AI
async function generalSettings() {
  const content = document.querySelector('#content');
  const d = state.settings = await api(`/api/guilds/${state.selected.id}/settings`);
  const c = d.config || {};
  content.innerHTML = `
    <div class="content">
      ${title('General & AI Configuration', 'Configure core bot behavior, prefixes, and AI assistant settings.', '<button class="button" id="save-btn">Save Changes</button>')}
      <div class="settings-grid">
        <article class="card">
          <div class="card-head"><div><h2>Server Prefix & Core</h2><p>Basic commands and interaction setup</p></div></div>
          <div class="field">
            <label>Command Prefix</label>
            <input data-setting="prefix" maxlength="5" value="${esc(c.prefix || '!')}" oninput="markUnsaved()">
            <span class="subtext">The prefix required before text commands (e.g. <code>!</code>, <code>?</code>, <code>.</code>).</span>
          </div>
          ${toggleSwitch('modlog_dm_notifications', 'DM Moderation Notifications', 'Send private DM messages to users when warned, muted, or kicked.', c.modlog_dm_notifications ?? true)}
        </article>
        <article class="card">
          <div class="card-head"><div><h2>AI Assistant Model</h2><p>Gemini, Groq, and OpenAI integrations</p></div></div>
          <div class="field">
            <label>AI Provider Backend</label>
            <div class="segmented-control" id="ai-provider-segmented">
              <button class="segmented-btn ${c.ai_provider === 'gemini' || !c.ai_provider ? 'active' : ''}" data-val="gemini">✦ Gemini 2.5</button>
              <button class="segmented-btn ${c.ai_provider === 'groq' ? 'active' : ''}" data-val="groq">⚡ Groq Llama-3</button>
              <button class="segmented-btn ${c.ai_provider === 'openai' ? 'active' : ''}" data-val="openai">🧠 OpenAI GPT</button>
            </div>
            <input type="hidden" data-setting="ai_provider" value="${esc(c.ai_provider || 'gemini')}">
            <span class="subtext">Select the backend model powering <code>!ask</code> and server context chats.</span>
          </div>
          <div class="field">
            <label>Dedicated AI Channel</label>
            ${channelSelect(d, 'ai_channel_id', c.ai_channel_id, 'If set, users can chat naturally without typing commands.')}
          </div>
        </article>
      </div>
    </div>
  `;

  document.querySelectorAll('#ai-provider-segmented .segmented-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('#ai-provider-segmented .segmented-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      document.querySelector('[data-setting="ai_provider"]').value = btn.dataset.val;
      markUnsaved();
    });
  });

  document.querySelector('#save-btn')?.addEventListener('click', () => saveSettings());
}

// Module 3: MULTI-LOGGING
async function loggingSettings() {
  const content = document.querySelector('#content');
  const d = state.settings = await api(`/api/guilds/${state.selected.id}/settings`);
  const c = d.config || {};
  const events = [
    ['message_log_channel_id', '🗑️ / ✏️ Messages Log', 'Track edited & deleted messages.'],
    ['join_leave_log_channel_id', '📥 / 📤 Member Join & Leave', 'Log new arrivals and member departures.'],
    ['role_update_log_channel_id', '👑 Role Changes', 'Log roles created, deleted, or assigned.'],
    ['voice_log_channel_id', '🎙️ Voice Activity', 'Track voice channel joins, leaves, and moves.'],
    ['channel_create_log_channel_id', '📁 Channel Creates', 'Log new channels created.'],
    ['channel_delete_log_channel_id', '📁 Channel Deletes', 'Log channel deletions.'],
    ['ban_unban_log_channel_id', '⚖️ Bans & Unbans', 'Track ban and unban events.']
  ];

  content.innerHTML = `
    <div class="content">
      ${title('Action Logging & Auditing', 'Granular multi-channel audit logs for all server activities.', '<button class="button" id="save-btn">Save Logging Channels</button>')}
      <div class="settings-grid">
        <article class="card">
          <div class="card-head"><div><h2>Primary Moderation Log</h2><p>Direct moderator commands output</p></div></div>
          <div class="field">
            <label>Mod Log Channel</label>
            ${channelSelect(d, 'mod_log_channel', c.mod_log_channel, 'Target channel for warns, mutes, kicks, bans, and purges.')}
          </div>
        </article>
        <article class="card">
          <div class="card-head"><div><h2>Multi-Channel Event Logging</h2><p>Route specific actions to dedicated log channels</p></div></div>
          ${events.map(([key, name, desc]) => `
            <div class="field" style="margin-bottom:14px;">
              <label>${name}</label>
              ${channelSelect(d, key, c[key], desc)}
            </div>
          `).join('')}
        </article>
      </div>
    </div>
  `;
  document.querySelector('#save-btn')?.addEventListener('click', () => saveSettings());
}

// Module 4: AUTOMOD
async function automodSettings() {
  const content = document.querySelector('#content');
  const d = state.settings = await api(`/api/guilds/${state.selected.id}/settings`);
  const c = d.config || {};
  content.innerHTML = `
    <div class="content">
      ${title('AutoMod Defense', 'Discord-native content protection and anti-spam filters.', '<button class="button" id="save-btn">Save AutoMod</button>')}
      <div class="settings-grid">
        <article class="card">
          <div class="card-head"><div><h2>Filter Protections</h2><p>Active content filtering rules</p></div></div>
          ${toggleSwitch('automod_enabled', 'Enable AutoMod Engine', 'Activate real-time server protection.', c.automod_enabled ?? true)}
          ${toggleSwitch('automod_block_invites', 'Block Discord Invites', 'Filter unauthorized discord.gg server invites.', c.automod_block_invites ?? true)}
          ${toggleSwitch('automod_block_scam', 'Anti-Phishing & Scam Filter', 'Block malicious links, nitro scams, and phishing domains.', c.automod_block_scam ?? true)}
          ${toggleSwitch('automod_block_markdown', 'Block Heading Markdown Spam', 'Filter massive # and ## heading font spam.', c.automod_block_markdown ?? false)}
        </article>
        <article class="card">
          <div class="card-head"><div><h2>Enforcement & Logging</h2><p>Action punishments on violations</p></div></div>
          <div class="field">
            <label>Violation Punishment</label>
            <div class="segmented-control" id="automod-punish-segmented">
              <button class="segmented-btn ${c.automod_punishment === 'block' || !c.automod_punishment ? 'active' : ''}" data-val="block">🛡️ Block</button>
              <button class="segmented-btn ${c.automod_punishment === 'timeout' ? 'active' : ''}" data-val="timeout">⏳ Timeout</button>
              <button class="segmented-btn ${c.automod_punishment === 'kick' ? 'active' : ''}" data-val="kick">👢 Kick</button>
              <button class="segmented-btn ${c.automod_punishment === 'ban' ? 'active' : ''}" data-val="ban">🔨 Ban</button>
            </div>
            <input type="hidden" data-setting="automod_punishment" value="${esc(c.automod_punishment || 'block')}">
            <span class="subtext">Punishment automatically applied when a member violates an AutoMod rule.</span>
          </div>
          <div class="field">
            <label>AutoMod Log Channel</label>
            ${channelSelect(d, 'automod_log_channel_id', c.automod_log_channel_id, 'Logs every filtered message and applied punishment.')}
          </div>
        </article>
      </div>
    </div>
  `;

  document.querySelectorAll('#automod-punish-segmented .segmented-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('#automod-punish-segmented .segmented-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      document.querySelector('[data-setting="automod_punishment"]').value = btn.dataset.val;
      markUnsaved();
    });
  });

  document.querySelector('#save-btn')?.addEventListener('click', () => saveSettings());
}

// Module 5: ANTI-NUKE
async function antinukeSettings() {
  const content = document.querySelector('#content');
  const d = state.settings = await api(`/api/guilds/${state.selected.id}/settings`);
  const c = d.config || {};
  content.innerHTML = `
    <div class="content">
      ${title('Anti-Nuke Defense Suite', 'Zero-tolerance server nuke and unauthorized admin defense.', '<button class="button" id="save-btn">Save Defense</button>')}
      <div class="settings-grid">
        <article class="card">
          <div class="card-head"><div><h2>Shield Activation</h2><p>Real-time threshold defense</p></div><span class="pill danger">ARMED</span></div>
          ${toggleSwitch('antinuke_enabled', 'Arm Anti-Nuke Shield', 'Monitor all channel, role, webhook, and mass-ban actions.', c.antinuke_enabled ?? false)}
          ${toggleSwitch('antinuke_strict', 'Strict Mode (1-Action Trigger)', 'Instantly ban any unwhitelisted admin on their first destructive action.', c.antinuke_strict ?? false)}
          ${toggleSwitch('antinuke_recovery', 'Auto Recovery', 'Automatically recreate deleted channels and restore roles if attacked.', c.antinuke_recovery ?? true)}
        </article>
        <article class="card">
          <div class="card-head"><div><h2>Enforcement Action</h2><p>Countermeasures against attackers</p></div></div>
          <div class="field">
            <label>Punishment Mode</label>
            <div class="segmented-control" id="antinuke-punish-segmented">
              <button class="segmented-btn ${c.antinuke_punishment === 'ban' || !c.antinuke_punishment ? 'active' : ''}" data-val="ban">🔨 Ban</button>
              <button class="segmented-btn ${c.antinuke_punishment === 'kick' ? 'active' : ''}" data-val="kick">👢 Kick</button>
              <button class="segmented-btn ${c.antinuke_punishment === 'strip_roles' ? 'active' : ''}" data-val="strip_roles">🚫 Strip Roles</button>
              <button class="segmented-btn ${c.antinuke_punishment === 'quarantine' ? 'active' : ''}" data-val="quarantine">🔒 Quarantine</button>
            </div>
            <input type="hidden" data-setting="antinuke_punishment" value="${esc(c.antinuke_punishment || 'ban')}">
            <span class="subtext">Action taken against unauthorized staff who exceed safety limits.</span>
          </div>
        </article>
      </div>
    </div>
  `;

  document.querySelectorAll('#antinuke-punish-segmented .segmented-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('#antinuke-punish-segmented .segmented-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      document.querySelector('[data-setting="antinuke_punishment"]').value = btn.dataset.val;
      markUnsaved();
    });
  });

  document.querySelector('#save-btn')?.addEventListener('click', () => saveSettings());
}

// Module 6: TICKET SYSTEM
async function ticketsManager() {
  const content = document.querySelector('#content');
  const [d, setD] = await Promise.all([
    api(`/api/guilds/${state.selected.id}/tickets`),
    api(`/api/guilds/${state.selected.id}/settings`)
  ]);
  state.settings = setD;
  const cfg = d.config || {};
  const panels = d.panels || [];
  const tickets = d.tickets || [];

  // Local builder state
  let editPanelId = null;
  let panelCategories = [
    { value: 'support', label: 'Support', emoji: '🛠️', description: 'General assistance and technical help' },
    { value: 'billing', label: 'Billing', emoji: '💳', description: 'Payment issues, store inquiries & donations' },
    { value: 'partnership', label: 'Partnership', emoji: '🤝', description: 'Server collaborations and sponsorships' },
    { value: 'report', label: 'Report', emoji: '📢', description: 'Report player misconduct or rule breaks' }
  ];

  function renderCategoryRows() {
    return panelCategories.map((cat, idx) => `
      <div style="display:flex;align-items:center;gap:10px;padding:8px 12px;background:var(--side);border:1px solid var(--line);border-radius:10px;margin-bottom:8px;">
        <input type="text" class="field-cat-emoji" data-idx="${idx}" value="${esc(cat.emoji || '📩')}" style="width:48px;text-align:center;padding:6px;border-radius:6px;background:var(--input-bg);border:1px solid var(--line);color:var(--ink);" title="Emoji">
        <input type="text" class="field-cat-label" data-idx="${idx}" value="${esc(cat.label || '')}" placeholder="Category Label" style="flex:1;padding:6px 10px;border-radius:6px;background:var(--input-bg);border:1px solid var(--line);color:var(--ink);">
        <input type="text" class="field-cat-desc" data-idx="${idx}" value="${esc(cat.description || '')}" placeholder="Short Description" style="flex:1.4;padding:6px 10px;border-radius:6px;background:var(--input-bg);border:1px solid var(--line);color:var(--ink);">
        <button class="button secondary del-cat-btn" data-idx="${idx}" style="padding:6px 10px;font-size:12px;color:var(--danger);border-color:rgba(239,68,68,0.3);" title="Remove Category">✕</button>
      </div>
    `).join('');
  }

  function updatePreview() {
    const titleVal = document.querySelector('#panel-title-input')?.value || 'Support Center';
    const descVal = document.querySelector('#panel-desc-input')?.value || 'Select a department below to create a private ticket with our staff.';
    const colorVal = document.querySelector('#panel-color-input')?.value || '#5865F2';
    const imgVal = document.querySelector('#panel-img-input')?.value || '';

    const previewEmbed = document.querySelector('#panel-preview-embed');
    if (!previewEmbed) return;

    previewEmbed.style.borderLeftColor = colorVal;
    const titleEl = previewEmbed.querySelector('.d-embed-title');
    if (titleEl) titleEl.textContent = `🎫 ${titleVal}`;
    const descEl = previewEmbed.querySelector('.d-embed-desc');
    if (descEl) descEl.textContent = descVal;

    const bannerEl = previewEmbed.querySelector('#preview-banner-img');
    if (bannerEl) {
      if (imgVal) {
        bannerEl.src = imgVal;
        bannerEl.style.display = 'block';
      } else {
        bannerEl.style.display = 'none';
      }
    }

    const selectEl = previewEmbed.querySelector('.d-select');
    if (selectEl) {
      selectEl.innerHTML = `
        <option value="">Select a ticket category...</option>
        ${panelCategories.map(c => `<option value="${esc(c.value)}">${esc(c.emoji || '📩')} ${esc(c.label)} — ${esc(c.description || '')}</option>`).join('')}
      `;
    }
  }

  content.innerHTML = `
    <div class="content">
      ${title('Ticket System Manager', 'Design, deploy, and edit custom ticket panels to any channel in real-time, configure routing & manage live tickets.', '<button class="button" id="save-ticket-btn">Save Ticket Routing</button>')}
      
      <!-- 1. DEPLOY & EDIT TICKET PANEL BUILDER -->
      <article class="card" style="margin-bottom:28px;">
        <div class="card-head">
          <div>
            <h2 id="builder-main-title">🎨 Custom Ticket Panel Embed Builder & Deployer</h2>
            <p id="builder-sub-title">Deploy an interactive ticket dropdown directly into any Discord channel on your server.</p>
          </div>
          <span class="pill green" id="builder-mode-pill">DEPLOY MODE</span>
        </div>

        <div style="display:grid;grid-template-columns:1.2fr 1fr;gap:24px;">
          <div>
            <div class="field">
              <label>Target Channel for Deployment *</label>
              ${channelSelect(setD, 'panel_target_channel_id', panels.length ? panels[0].channel_id : '', 'Select the text channel where this interactive panel will be posted.')}
            </div>

            <div class="field">
              <label>Panel Embed Title</label>
              <input type="text" id="panel-title-input" value="Support Center" placeholder="e.g. Server Support & Complaints">
            </div>

            <div class="field">
              <label>Panel Description & Instructions</label>
              <textarea id="panel-desc-input" rows="3" style="width:100%;border:1px solid var(--line);border-radius:12px;background:var(--input-bg);padding:12px;color:var(--ink);font:600 13px 'Manrope',sans-serif;resize:vertical;" placeholder="Select a department below to create a private ticket with our staff.">Need assistance, have billing inquiries, or want to submit a report?
Select the appropriate department below to open a private ticket with our staff.</textarea>
            </div>

            <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;">
              <div class="field">
                <label>Embed Accent Color</label>
                <div style="display:flex;gap:8px;align-items:center;">
                  <input type="color" id="panel-color-picker" value="#5865f2" style="width:40px;height:40px;border-radius:8px;border:1px solid var(--line);background:transparent;cursor:pointer;">
                  <input type="text" id="panel-color-input" value="#5865F2" style="flex:1;">
                </div>
              </div>
              <div class="field">
                <label>Banner Image URL (Optional)</label>
                <input type="text" id="panel-img-input" placeholder="https://i.imgur.com/example.png">
              </div>
            </div>

            <div style="margin-top:16px;">
              <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px;">
                <label style="font-weight:700;font-size:12px;color:var(--ink-secondary);">Category Dropdown Options</label>
                <button class="button secondary" id="add-cat-btn" style="padding:4px 10px;font-size:11.5px;">+ Add Category</button>
              </div>
              <div id="category-rows-container">
                ${renderCategoryRows()}
              </div>
            </div>

            <div style="display:flex;gap:12px;margin-top:20px;">
              <button class="button" id="deploy-panel-submit-btn" style="flex:1;">🚀 Deploy Ticket Panel to Discord</button>
              <button class="button secondary" id="cancel-edit-btn" style="display:none;">Cancel Edit</button>
            </div>
          </div>

          <!-- LIVE DISCORD PREVIEW -->
          <div>
            <div style="font:800 11px 'Fira Code',monospace;color:var(--muted);letter-spacing:0.08em;margin-bottom:10px;">LIVE DISCORD EMBED PREVIEW</div>
            <div class="d-embed" id="panel-preview-embed" style="margin-top:0;border-left:4px solid #5865F2;">
              <div class="d-embed-author">🎫 HELIX AUTOMATED SUPPORT CENTER</div>
              <div class="d-embed-title">🎫 Support Center</div>
              <div class="d-embed-desc">Need assistance, have billing inquiries, or want to submit a report? Select the appropriate department below to open a private ticket with our staff.</div>
              <img id="preview-banner-img" src="" style="width:100%;border-radius:6px;margin-bottom:10px;display:none;max-height:180px;object-fit:cover;" alt="Banner">
              <div class="d-select-wrap">
                <select class="d-select" disabled>
                  <option value="">Select a ticket category...</option>
                  ${panelCategories.map(c => `<option>${esc(c.emoji || '📩')} ${esc(c.label)} — ${esc(c.description || '')}</option>`).join('')}
                </select>
              </div>
              <div class="d-embed-footer">
                <span>Select a category below to open a ticket</span>
              </div>
            </div>
          </div>
        </div>
      </article>

      <!-- 2. DEPLOYED PANELS LIST -->
      <article class="card" style="margin-bottom:28px;">
        <div class="card-head">
          <div>
            <h2>Active Deployed Panels (${panels.length})</h2>
            <p>Manage, re-edit, or remove ticket panels active in your channels</p>
          </div>
        </div>

        ${panels.length === 0 ? `
          <div class="empty-state">
            <strong>No Ticket Panels Deployed Yet</strong>
            <p>Use the builder above or the Discord command <code>!ticket builder</code> to post your first panel!</p>
          </div>
        ` : `
          <div style="display:grid;grid-template-columns:repeat(auto-fill, minmax(320px, 1fr));gap:16px;">
            ${panels.map(p => {
              let pOpts = [];
              try { pOpts = JSON.parse(p.options_json || '[]'); } catch (e) {}
              const chName = (setD.channels || []).find(c => String(c.id) === String(p.channel_id))?.name || p.channel_id;
              return `
                <div style="background:var(--side);border:1px solid var(--line);border-radius:14px;padding:18px;display:flex;flex-direction:column;justify-content:space-between;box-shadow:var(--card-inner-glow);">
                  <div>
                    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;">
                      <span class="pill" style="font-size:10px;">ID #${p.id}</span>
                      <span class="pill green">#${esc(chName)}</span>
                    </div>
                    <h3 style="margin:0 0 6px;font-size:16px;color:var(--ink);">${esc(p.title || 'Support Center')}</h3>
                    <p style="margin:0 0 12px;font-size:12.5px;color:var(--ink-secondary);line-height:1.5;">${esc(p.description || '')}</p>
                    <div style="font:700 11px 'Fira Code',monospace;color:var(--muted);margin-bottom:12px;">
                      ${pOpts.length} Categories: ${pOpts.map(o => o.emoji || '📩').join(' ')}
                    </div>
                  </div>
                  <div style="display:flex;gap:8px;border-top:1px solid var(--line);padding-top:12px;">
                    <button class="button secondary edit-panel-btn" data-panel-id="${p.id}" style="flex:1;padding:7px;font-size:12px;">✏️ Edit Panel</button>
                    <button class="button secondary del-panel-btn" data-panel-id="${p.id}" style="padding:7px 12px;font-size:12px;color:var(--danger);border-color:rgba(239,68,68,0.3);">🗑️ Delete</button>
                  </div>
                </div>
              `;
            }).join('')}
          </div>
        `}
      </article>

      <!-- 3. GLOBAL ROUTING & SETTINGS -->
      <div class="settings-grid" style="margin-bottom:28px;">
        <article class="card">
          <div class="card-head"><div><h2>Category & Channel Routing</h2><p>Per-guild open/closed ticket organization</p></div></div>
          <div class="field">
            <label>Open Tickets Category</label>
            ${categorySelect(setD, 'ticket_open_category_id', cfg.open_category_id, 'New tickets will be created inside this category.')}
          </div>
          <div class="field">
            <label>Closed Tickets Category</label>
            ${categorySelect(setD, 'ticket_closed_category_id', cfg.closed_category_id, 'Closed tickets are automatically moved here.')}
          </div>
          <div class="field">
            <label>Support Staff Role</label>
            ${roleSelect(setD, 'ticket_staff_role_id', cfg.staff_role_id, 'Role with permissions to claim and manage tickets.')}
          </div>
          <div class="field">
            <label>HTML Transcript Log Channel</label>
            ${channelSelect(setD, 'ticket_transcript_channel_id', cfg.transcript_channel_id, 'All interactive HTML transcripts are sent here upon ticket closure.')}
          </div>
        </article>

        <article class="card">
          <div class="card-head"><div><h2>Ticket Telemetry & Status</h2><p>Live metrics & ticket counters</p></div></div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:20px;">
            <div style="background:var(--side);padding:16px;border-radius:12px;border:1px solid var(--line);">
              <span style="font-size:11px;color:var(--muted);font-weight:700;">NEXT TICKET NUMBER</span>
              <strong style="display:block;font-size:24px;color:var(--ink);font-family:'Fira Code',monospace;margin-top:4px;">#${String(cfg.next_ticket_number || 1).padStart(4,'0')}</strong>
            </div>
            <div style="background:var(--side);padding:16px;border-radius:12px;border:1px solid var(--line);">
              <span style="font-size:11px;color:var(--muted);font-weight:700;">ACTIVE PANELS</span>
              <strong style="display:block;font-size:24px;color:var(--good);font-family:'Fira Code',monospace;margin-top:4px;">${panels.length}</strong>
            </div>
          </div>
          <div style="font-size:13px;color:var(--ink-secondary);line-height:1.6;">
            💡 <b>Discord Staff Commands Available:</b><br>
            • <code>!ticket builder</code> — Interactive in-Discord visual embed creator.<br>
            • <code>!ticket deploy #channel</code> — Fast deployment of support panel.<br>
            • <code>!ticket close</code> / <code>!ticket reopen</code> — Lock or restore tickets.<br>
            • <code>!ticket transcript</code> — Export full HTML transcript.
          </div>
        </article>
      </div>

      <!-- 4. RECENT TICKET QUEUE -->
      <article class="card">
        <div class="card-head"><div><h2>Recent Ticket Queue</h2><p>${tickets.length} recent tickets in database</p></div></div>
        ${tickets.length === 0 ? `
          <div class="empty-state">
            <strong>No Tickets Created Yet</strong>
            <p>When users open tickets via the panel dropdown, they will appear here live.</p>
          </div>
        ` : `
          <div class="table-wrap">
            <table class="table">
              <thead>
                <tr>
                  <th>Ticket #</th>
                  <th>Status</th>
                  <th>Department</th>
                  <th>User</th>
                  <th>Claimed By</th>
                  <th>Created</th>
                  <th style="text-align:right;">Actions</th>
                </tr>
              </thead>
              <tbody>
                ${tickets.map(t => `
                  <tr>
                    <td><b>#${String(t.ticket_number || t.id).padStart(4, '0')}</b></td>
                    <td><span class="pill ${t.status === 'closed' ? 'closed' : 'green'}">${esc((t.status || 'open').toUpperCase())}</span></td>
                    <td><span class="pill">${esc(t.ticket_type || 'General')}</span></td>
                    <td>User ${esc(t.user_id)}</td>
                    <td>${t.claimed_by ? `<span class="pill">Mod ${esc(t.claimed_by)}</span>` : '<span class="subtext">Unclaimed</span>'}</td>
                    <td>${esc(formatDate(t.created_at))}</td>
                    <td style="text-align:right;">
                      ${t.status !== 'closed' ? `
                        <button class="button secondary close-ticket-btn" data-ticket-id="${t.id}" style="padding:5px 10px;font-size:11px;color:var(--danger);border-color:rgba(239,68,68,0.3);">🔒 Close</button>
                      ` : `
                        <span class="subtext">Archived</span>
                      `}
                    </td>
                  </tr>
                `).join('')}
              </tbody>
            </table>
          </div>
        `}
      </article>
    </div>
  `;

  // Color picker sync
  document.querySelector('#panel-color-picker')?.addEventListener('input', (e) => {
    const hex = e.target.value.toUpperCase();
    document.querySelector('#panel-color-input').value = hex;
    updatePreview();
  });
  document.querySelector('#panel-color-input')?.addEventListener('input', (e) => {
    const hex = e.target.value;
    if (/^#[0-9A-Fa-f]{6}$/.test(hex)) {
      document.querySelector('#panel-color-picker').value = hex;
    }
    updatePreview();
  });
  document.querySelector('#panel-title-input')?.addEventListener('input', updatePreview);
  document.querySelector('#panel-desc-input')?.addEventListener('input', updatePreview);
  document.querySelector('#panel-img-input')?.addEventListener('input', updatePreview);

  // Category Option Events
  function bindCategoryEvents() {
    document.querySelectorAll('.field-cat-emoji').forEach(el => {
      el.addEventListener('input', (e) => {
        const idx = parseInt(e.target.dataset.idx);
        panelCategories[idx].emoji = e.target.value;
        updatePreview();
      });
    });
    document.querySelectorAll('.field-cat-label').forEach(el => {
      el.addEventListener('input', (e) => {
        const idx = parseInt(e.target.dataset.idx);
        panelCategories[idx].label = e.target.value;
        panelCategories[idx].value = e.target.value.toLowerCase().replace(/\s+/g, '_').substring(0, 30);
        updatePreview();
      });
    });
    document.querySelectorAll('.field-cat-desc').forEach(el => {
      el.addEventListener('input', (e) => {
        const idx = parseInt(e.target.dataset.idx);
        panelCategories[idx].description = e.target.value;
        updatePreview();
      });
    });
    document.querySelectorAll('.del-cat-btn').forEach(el => {
      el.addEventListener('click', (e) => {
        const idx = parseInt(e.target.dataset.idx);
        panelCategories.splice(idx, 1);
        document.querySelector('#category-rows-container').innerHTML = renderCategoryRows();
        bindCategoryEvents();
        updatePreview();
      });
    });
  }
  bindCategoryEvents();

  document.querySelector('#add-cat-btn')?.addEventListener('click', () => {
    panelCategories.push({ value: `category_${panelCategories.length + 1}`, label: `Department ${panelCategories.length + 1}`, emoji: '📩', description: 'Assistance for this department' });
    document.querySelector('#category-rows-container').innerHTML = renderCategoryRows();
    bindCategoryEvents();
    updatePreview();
  });

  // Deploy / Update Button Handler
  document.querySelector('#deploy-panel-submit-btn')?.addEventListener('click', async () => {
    const chanId = document.querySelector('[data-setting="panel_target_channel_id"]')?.value;
    const titleVal = document.querySelector('#panel-title-input')?.value || 'Support Center';
    const descVal = document.querySelector('#panel-desc-input')?.value || 'Select a department below to create a private ticket.';
    const colorVal = document.querySelector('#panel-color-input')?.value || '#5865F2';
    const imgVal = document.querySelector('#panel-img-input')?.value || null;

    if (!editPanelId && (!chanId || chanId === 'null')) {
      toast('Please select a target channel for deployment.', true);
      return;
    }

    try {
      if (editPanelId) {
        // Edit existing panel
        await api(`/api/guilds/${state.selected.id}/tickets/panels/${editPanelId}`, {
          method: 'PUT',
          body: JSON.stringify({
            title: titleVal,
            description: descVal,
            color_hex: colorVal,
            image_url: imgVal,
            options: panelCategories
          })
        });
        toast('Ticket panel successfully updated on Discord!');
      } else {
        // Deploy new panel
        await api(`/api/guilds/${state.selected.id}/tickets/panels/deploy`, {
          method: 'POST',
          body: JSON.stringify({
            channel_id: chanId,
            title: titleVal,
            description: descVal,
            color_hex: colorVal,
            image_url: imgVal,
            options: panelCategories
          })
        });
        toast('🚀 Ticket panel successfully deployed to Discord!');
      }
      ticketsManager(); // Refresh view
    } catch (err) {
      toast(err.message, true);
    }
  });

  // Edit Panel Click
  document.querySelectorAll('.edit-panel-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      const pId = parseInt(e.target.dataset.panelId);
      const targetPanel = panels.find(p => p.id === pId);
      if (!targetPanel) return;

      editPanelId = pId;
      document.querySelector('#builder-main-title').textContent = `✏️ Edit Ticket Panel #${pId}`;
      document.querySelector('#builder-sub-title').textContent = 'Modify panel properties below. Clicking Update will edit the live message in Discord instantly.';
      document.querySelector('#builder-mode-pill').textContent = 'EDIT MODE';
      document.querySelector('#builder-mode-pill').className = 'pill';
      document.querySelector('#deploy-panel-submit-btn').textContent = '🔄 Update Discord Panel';
      document.querySelector('#cancel-edit-btn').style.display = 'inline-flex';

      document.querySelector('#panel-title-input').value = targetPanel.title || '';
      document.querySelector('#panel-desc-input').value = targetPanel.description || '';
      document.querySelector('#panel-color-input').value = targetPanel.embed_color || '#5865F2';
      document.querySelector('#panel-color-picker').value = targetPanel.embed_color || '#5865F2';

      try {
        panelCategories = JSON.parse(targetPanel.options_json || '[]');
      } catch (err) {
        panelCategories = [];
      }
      document.querySelector('#category-rows-container').innerHTML = renderCategoryRows();
      bindCategoryEvents();
      updatePreview();
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
  });

  // Cancel Edit Click
  document.querySelector('#cancel-edit-btn')?.addEventListener('click', () => {
    editPanelId = null;
    ticketsManager();
  });

  // Delete Panel Click
  document.querySelectorAll('.del-panel-btn').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      const pId = parseInt(e.target.dataset.panelId);
      if (!confirm(`Are you sure you want to delete ticket panel #${pId}? This will remove it from the database and remove the Discord message.`)) return;

      try {
        await api(`/api/guilds/${state.selected.id}/tickets/panels/${pId}`, { method: 'DELETE' });
        toast(`Ticket panel #${pId} deleted.`);
        ticketsManager();
      } catch (err) {
        toast(err.message, true);
      }
    });
  });

  // Close Ticket Button Click
  document.querySelectorAll('.close-ticket-btn').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      const tId = parseInt(e.target.dataset.ticketId);
      if (!confirm(`Close ticket #${tId}? Normal user permissions will be locked and channel archived.`)) return;

      try {
        await api(`/api/guilds/${state.selected.id}/tickets/close/${tId}`, { method: 'POST' });
        toast(`Ticket #${tId} closed successfully.`);
        ticketsManager();
      } catch (err) {
        toast(err.message, true);
      }
    });
  });

  // Global Config Save Handler
  document.querySelector('#save-ticket-btn')?.addEventListener('click', async () => {
    const open_cat = document.querySelector('[data-setting="ticket_open_category_id"]')?.value || null;
    const closed_cat = document.querySelector('[data-setting="ticket_closed_category_id"]')?.value || null;
    const staff_role = document.querySelector('[data-setting="ticket_staff_role_id"]')?.value || null;
    const trans_chan = document.querySelector('[data-setting="ticket_transcript_channel_id"]')?.value || null;

    try {
      await api(`/api/guilds/${state.selected.id}/tickets/config`, {
        method: 'POST',
        body: JSON.stringify({
          open_category_id: open_cat,
          closed_category_id: closed_cat,
          staff_role_id: staff_role,
          transcript_channel_id: trans_chan
        })
      });
      clearUnsaved();
      toast('Ticket routing configuration saved!');
    } catch (e) {
      toast(e.message, true);
    }
  });
}

// Module 7: LEVELING
async function levelingSettings() {
  const content = document.querySelector('#content');
  const d = state.settings = await api(`/api/guilds/${state.selected.id}/settings`);
  const c = d.config || {};
  content.innerHTML = `
    <div class="content">
      ${title('Leveling & Chat XP', 'Configure XP rewards, level announcement channels, and cooldowns.', '<button class="button" id="save-btn">Save Leveling</button>')}
      <div class="settings-grid">
        <article class="card">
          <div class="card-head"><div><h2>XP Engine Settings</h2><p>Message activity rewards</p></div></div>
          ${toggleSwitch('xp_enabled', 'Enable Chat XP', 'Award members XP for participating in conversations.', c.xp_enabled ?? true)}
          <div class="field">
            <label>XP Earned Per Message</label>
            <input data-setting="xp_per_message" type="number" min="1" max="100" value="${Number(c.xp_per_message || 10)}" oninput="markUnsaved()">
          </div>
          <div class="field">
            <label>XP Cooldown (Seconds)</label>
            <input data-setting="xp_cooldown_seconds" type="number" min="0" max="300" value="${Number(c.xp_cooldown_seconds || 60)}" oninput="markUnsaved()">
          </div>
        </article>
        <article class="card">
          <div class="card-head"><div><h2>Announcements</h2><p>Level up celebratory messages</p></div></div>
          <div class="field">
            <label>Level Up Channel</label>
            ${channelSelect(d, 'level_channel_id', c.level_channel_id, 'Leave blank to post level ups in the active chat channel.')}
          </div>
        </article>
      </div>
    </div>
  `;
  document.querySelector('#save-btn')?.addEventListener('click', () => saveSettings());
}

// Module 8: GIVEAWAYS
async function giveawaysManager() {
  const content = document.querySelector('#content');
  const d = await api(`/api/guilds/${state.selected.id}/giveaways`);
  content.innerHTML = `
    <div class="content">
      ${title('Giveaway Management', 'View live and concluded giveaways hosted by Helix.')}
      <article class="card">
        <div class="card-head"><div><h2>Active & Past Giveaways</h2><p>${(d.giveaways || []).length} recorded giveaway events</p></div></div>
        ${table(d.giveaways || [], ['prize','winners_count','end_time','ended'], {
          prize: v => `🎁 <b>${esc(v)}</b>`,
          winners_count: v => `${v} winner${v === 1 ? '' : 's'}`,
          ended: v => `<span class="pill ${v ? 'closed' : 'green'}">${v ? 'ENDED' : 'ACTIVE'}</span>`,
          end_time: v => esc(formatDate(v))
        })}
      </article>
    </div>
  `;
}

// Module 9: ECONOMY
async function economyManager() {
  const content = document.querySelector('#content');
  const d = await api(`/api/guilds/${state.selected.id}/economy`);
  content.innerHTML = `
    <div class="content">
      ${title('Economy & Server Shop', 'Server wealth leaderboard and custom shop items.')}
      <div class="settings-grid">
        <article class="card">
          <div class="card-head"><div><h2>Top Richest Members</h2><p>Net worth leaderboard</p></div></div>
          ${table(d.leaderboard || [], ['user_id','wallet','bank','net_worth'], {
            user_id: v => `User ${v}`,
            wallet: v => `🪙 ${Number(v || 0).toLocaleString()}`,
            bank: v => `🏦 ${Number(v || 0).toLocaleString()}`,
            net_worth: v => `<b>🪙 ${Number(v || 0).toLocaleString()}</b>`
          })}
        </article>
        <article class="card">
          <div class="card-head"><div><h2>Server Shop Items</h2><p>Available items in <code>!shop</code></p></div></div>
          ${table(d.shop_items || [], ['name','price','description'], {
            name: v => `✨ <b>${esc(v)}</b>`,
            price: v => `🪙 ${Number(v || 0).toLocaleString()}`,
            description: v => esc(v || 'No description')
          })}
        </article>
      </div>
    </div>
  `;
}

// Module 10: VANITY
async function vanityManager() {
  const content = document.querySelector('#content');
  const d = await api(`/api/guilds/${state.selected.id}/vanity`);
  content.innerHTML = `
    <div class="content">
      ${title('Vanity URL Tracker', 'Active real-time vanity URL monitoring.')}
      <article class="card">
        <div class="card-head"><div><h2>Tracked Discord Vanities</h2><p>${(d.vanities || []).length} active monitors</p></div></div>
        ${table(d.vanities || [], ['vanity_code','user_id','created_at'], {
          vanity_code: v => `discord.gg/<b>${esc(v)}</b>`,
          user_id: v => `User ${v}`,
          created_at: v => esc(formatDate(v))
        })}
      </article>
    </div>
  `;
}

// Module: COMMUNITY & ONBOARDING (Auto Roles, Welcome & Starboard)
async function communityManager() {
  const content = document.querySelector('#content');
  const d = await api(`/api/guilds/${state.selected.id}/overview`);
  const cData = await api(`/api/guilds/${state.selected.id}/community`);
  const w = cData.welcome || {};
  const sb = cData.starboard || {};
  const humanRoles = (cData.autoroles || []).filter(r => r.is_bot === 0).map(r => String(r.role_id));
  const botRoles = (cData.autoroles || []).filter(r => r.is_bot === 1).map(r => String(r.role_id));

  content.innerHTML = `
    <div class="content">
      ${title('Auto Roles, Welcome & Starboard', 'Configure automated role assignment on join, luxury welcome cards, and community showcase channels.', '<button class="button" id="save-community-btn">Save Community Settings ➔</button>')}

      <div class="grid-2">
        <!-- 1. AUTO ROLES -->
        <article class="card">
          <div class="card-head">
            <div>
              <h2>👥 Auto Roles on Join</h2>
              <p>Automatically assign roles to new members and bots when they join</p>
            </div>
            <span class="pill green">AUTOMATION</span>
          </div>

          <div class="form-group">
            <label>Human Member Auto Roles</label>
            <span class="subtext">Select roles granted to real users upon joining.</span>
            ${multiRoleSelect(d, 'comm_human_roles', humanRoles)}
          </div>

          <div class="form-group">
            <label>Bot Auto Roles</label>
            <span class="subtext">Select roles automatically assigned to bots upon joining.</span>
            ${multiRoleSelect(d, 'comm_bot_roles', botRoles)}
          </div>
        </article>

        <!-- 2. STARBOARD SHOWCASE -->
        <article class="card">
          <div class="card-head">
            <div>
              <h2>⭐ Starboard Showcase</h2>
              <p>Automatically pin and highlight community favorites</p>
            </div>
            <span class="pill gold">SHOWCASE</span>
          </div>

          <div class="form-group">
            <label class="toggle-wrap">
              <input type="checkbox" id="comm_sb_enabled" ${sb.is_enabled !== 0 ? 'checked' : ''}>
              <span class="toggle-slider"></span>
              <span class="toggle-label">Enable Starboard System</span>
            </label>
          </div>

          <div class="form-group">
            <label>Starboard Channel</label>
            <span class="subtext">Channel where starred messages will be posted.</span>
            ${channelSelect(d, 'comm_sb_channel', sb.channel_id, 'Select starboard channel...')}
          </div>

          <div class="grid-2" style="gap:12px;">
            <div class="form-group">
              <label>Reaction Threshold</label>
              <input type="number" id="comm_sb_threshold" min="1" max="50" value="${sb.threshold || 3}">
            </div>
            <div class="form-group">
              <label>Trigger Emoji</label>
              <input type="text" id="comm_sb_emoji" value="${esc(sb.emoji || '⭐')}" placeholder="⭐">
            </div>
          </div>
        </article>
      </div>

      <!-- 3. WELCOME & GOODBYE SYSTEM -->
      <article class="card" style="margin-top:20px;">
        <div class="card-head">
          <div>
            <h2>👋 Welcome & Goodbye Announcements</h2>
            <p>Customize member arrival and departure messages, canvas cards, and private DMs</p>
          </div>
          <span class="pill">CANVAS ENGINE</span>
        </div>

        <div class="form-group">
          <label class="toggle-wrap">
            <input type="checkbox" id="comm_w_enabled" ${w.is_enabled !== 0 ? 'checked' : ''}>
            <span class="toggle-slider"></span>
            <span class="toggle-label">Enable Welcome Announcements</span>
          </label>
        </div>

        <div class="grid-2" style="gap:16px;">
          <div class="form-group">
            <label>Welcome Channel</label>
            <span class="subtext">Channel for new member arrival notices.</span>
            ${channelSelect(d, 'comm_w_channel', w.welcome_channel_id, 'Select welcome channel...')}
          </div>

          <div class="form-group">
            <label>Goodbye / Leave Channel</label>
            <span class="subtext">Channel for member departure notices.</span>
            ${channelSelect(d, 'comm_g_channel', w.goodbye_channel_id, 'Select departure channel...')}
          </div>
        </div>

        <div class="grid-2" style="gap:16px;">
          <div class="form-group">
            <label>Visual Presentation Style</label>
            <span class="subtext">Choose how welcome announcements are rendered.</span>
            <select id="comm_w_type">
              <option value="card" ${w.welcome_type === 'card' || !w.welcome_type ? 'selected' : ''}>🖼️ Luxury Canvas PNG Card (Pillow Engine)</option>
              <option value="embed" ${w.welcome_type === 'embed' ? 'selected' : ''}>💎 Rich Obsidian & Crimson Embed</option>
              <option value="text" ${w.welcome_type === 'text' ? 'selected' : ''}>💬 Plain Text Message</option>
            </select>
          </div>

          <div class="form-group">
            <label class="toggle-wrap" style="margin-top:24px;">
              <input type="checkbox" id="comm_w_dm" ${w.dm_enabled === 1 ? 'checked' : ''}>
              <span class="toggle-slider"></span>
              <span class="toggle-label">Send Welcome Embed in Direct Message (DM)</span>
            </label>
          </div>
        </div>

        <div class="form-group">
          <label>Custom Welcome Message Text</label>
          <span class="subtext">Placeholders: <code>{user}</code> (mention), <code>{user.name}</code> (username), <code>{server}</code> (server name), <code>{membercount}</code> (member count).</span>
          <textarea id="comm_w_msg" rows="3" placeholder="Welcome to {server}, {user}! You are member #{membercount} 🎉">${esc(w.welcome_msg || 'Welcome to {server}, {user}! You are member #{membercount} 🎉')}</textarea>
        </div>

        <div class="form-group">
          <label>Custom Goodbye / Leave Message Text</label>
          <textarea id="comm_g_msg" rows="2" placeholder="{user.name} has left the server. We now have {membercount} members.">${esc(w.goodbye_msg || '{user.name} has left the server. We now have {membercount} members.')}</textarea>
        </div>
      </article>
    </div>
  `;

  document.querySelector('#save-community-btn')?.addEventListener('click', async () => {
    const humanRolesSelected = Array.from(document.querySelectorAll('#comm_human_roles option:checked')).map(o => o.value);
    const botRolesSelected = Array.from(document.querySelectorAll('#comm_bot_roles option:checked')).map(o => o.value);

    const payload = {
      human_roles: humanRolesSelected,
      bot_roles: botRolesSelected,
      welcome: {
        welcome_channel_id: document.querySelector('#comm_w_channel')?.value || null,
        goodbye_channel_id: document.querySelector('#comm_g_channel')?.value || null,
        welcome_type: document.querySelector('#comm_w_type')?.value || 'card',
        welcome_msg: document.querySelector('#comm_w_msg')?.value || null,
        goodbye_msg: document.querySelector('#comm_g_msg')?.value || null,
        dm_enabled: document.querySelector('#comm_w_dm')?.checked || false,
        is_enabled: document.querySelector('#comm_w_enabled')?.checked || true
      },
      starboard: {
        channel_id: document.querySelector('#comm_sb_channel')?.value || null,
        threshold: Number(document.querySelector('#comm_sb_threshold')?.value || 3),
        emoji: document.querySelector('#comm_sb_emoji')?.value || '⭐',
        is_enabled: document.querySelector('#comm_sb_enabled')?.checked || true
      }
    };

    try {
      await api(`/api/guilds/${state.selected.id}/community`, {
        method: 'POST',
        body: JSON.stringify(payload)
      });
      toast('Community, Auto Roles & Welcome settings saved successfully!');
    } catch (e) {
      toast(e.message, true);
    }
  });
}

// Module 11: MOD LOG
async function activityLog() {
  const content = document.querySelector('#content');
  const d = await api(`/api/guilds/${state.selected.id}/activity`);
  content.innerHTML = `
    <div class="content">
      ${title('Moderation Audit Trail', 'Complete historical record of moderation actions in this server.')}
      <article class="card">
        <div class="card-head"><div><h2>Recorded Actions</h2><p>Read-only audit log for server safety</p></div></div>
        ${table(d.activity || [], ['action','target_id','moderator_id','reason','created_at'], {
          action: v => `<span class="pill ${['ban','hackban'].includes(v) ? 'danger' : ''}">${esc(v).toUpperCase()}</span>`,
          target_id: v => `User ${v}`,
          moderator_id: v => `Mod ${v}`,
          reason: v => esc(v || 'No reason provided'),
          created_at: v => esc(formatDate(v))
        })}
      </article>
    </div>
  `;
}

async function saveSettings(extraPatch = {}) {
  const patch = { ...extraPatch };
  document.querySelectorAll('[data-setting]').forEach(el => {
    if (el.type === 'checkbox') patch[el.dataset.setting] = el.checked;
    else if (el.type === 'number') patch[el.dataset.setting] = Number(el.value);
    else patch[el.dataset.setting] = el.value || null;
  });

  try {
    const r = await api(`/api/guilds/${state.selected.id}/settings`, {
      method: 'PUT',
      body: JSON.stringify({ patch })
    });
    if (state.settings) state.settings.config = r.config;
    clearUnsaved();
    toast('Settings successfully saved to Helix!');
  } catch (e) {
    toast(e.message, true);
  }
}

function table(rows, columns, format = {}) {
  if (!rows || !rows.length) return '<div class="empty-state"><strong>Nothing recorded yet</strong>Helix will populate this section as events occur.</div>';
  return `
    <div class="table-wrap">
      <table class="table">
        <thead>
          <tr>${columns.map(c => `<th>${esc(c.replaceAll('_',' ').toUpperCase())}</th>`).join('')}</tr>
        </thead>
        <tbody>
          ${rows.map(row => `<tr>${columns.map(c => `<td>${format[c] ? format[c](row[c]) : esc(row[c] ?? '—')}</td>`).join('')}</tr>`).join('')}
        </tbody>
      </table>
    </div>
  `;
}

function formatDate(v) {
  if (!v) return '—';
  const d = new Date(v.endsWith('Z') ? v : `${v}Z`);
  return Number.isNaN(d) ? v : d.toLocaleString();
}

// ----------------------------------------------------
// INITIALIZATION
// ----------------------------------------------------
async function init() {
  try {
    state.me = await api('/api/me');
    if (state.me.authenticated) {
      const gResp = await api('/api/guilds');
      state.guilds = gResp.guilds || [];
    }
  } catch (e) {
    console.warn('Helix API check:', e);
  }
  showLanding();
}

init();
