// --- DATA LAYER CONFIG & BACKEND PROBE ---
const API_BASE = "/api";
const ENDPOINTS = {
    summary: `${API_BASE}/tasks/summary/`,
    today: `${API_BASE}/tasks/today/`,
    upcoming: `${API_BASE}/tasks/upcoming/`,
    tasks: `${API_BASE}/tasks/`,
    voice: `${API_BASE}/tasks/from-voice/`,
    voiceCommand: `${API_BASE}/voice/command/`,
    voiceAudio: `${API_BASE}/voice/audio/`,
    aiSummary: `${API_BASE}/ai/summary/`,
    aiMorning: `${API_BASE}/ai/morning/`,
    aiEvening: `${API_BASE}/ai/evening/`,
    tools: `${API_BASE}/tools/`,
    login: `${API_BASE}/accounts/login/`,
    register: `${API_BASE}/accounts/register/`,
    verifyAccount: `${API_BASE}/accounts/verify-account/`,
    passwordResetRequest: `${API_BASE}/accounts/password-reset/request/`,
    passwordResetConfirm: `${API_BASE}/accounts/password-reset/confirm/`,
    profile: `${API_BASE}/accounts/profile/`,
    changeEmail: `${API_BASE}/accounts/change-email/`,
    deleteAccount: `${API_BASE}/accounts/delete-account/`,
    logout: `${API_BASE}/accounts/logout/`
};

function getCSRFToken() {
    const fromCookie = document.cookie.split(';').find(c => c.trim().startsWith('csrftoken='));
    if (fromCookie) {
        return fromCookie.trim().split('=')[1];
    }

    const fromMeta = document.querySelector('meta[name="csrf-token"]');
    if (fromMeta) {
        return fromMeta.getAttribute('content');
    }

    const fromInput = document.querySelector('input[name="csrfmiddlewaretoken"]');
    if (fromInput) {
        return fromInput.value;
    }

    return '';
}

async function apiFetch(url, options = {}) {
    const csrfToken = getCSRFToken();
    if (!csrfToken) {
        console.warn('Missing CSRF token for apiFetch request to', url);
    }

    const defaults = {
        credentials: 'include',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken
        }
    };

    return fetch(url, {
        ...defaults,
        ...options,
        headers: {
            ...defaults.headers,
            ...options.headers
        }
    });
}

async function apiFetchForm(url, formData, options = {}) {
    const csrfToken = getCSRFToken();
    if (!csrfToken) {
        console.warn('Missing CSRF token for apiFetchForm request to', url);
    }

    const fetchOptions = {
        credentials: 'include',
        method: options.method || 'POST',
        headers: {
            'X-CSRFToken': csrfToken,
            ...(options.headers || {})
        },
        body: formData,
        ...options
    };

    return fetch(url, fetchOptions);
}

function setButtonLoading(button, isLoading, label = 'Processing...') {
    if (!button) return;
    if (isLoading) {
        button.dataset.originalText = button.textContent;
        button.disabled = true;
        button.classList.add('is-loading');
        button.textContent = label;
    } else {
        button.disabled = false;
        button.classList.remove('is-loading');
        if (button.dataset.originalText) {
            button.textContent = button.dataset.originalText;
            delete button.dataset.originalText;
        }
    }
}

async function withButtonLoading(button, callback, label = 'Processing...') {
    setButtonLoading(button, true, label);
    try {
        return await callback();
    } finally {
        setButtonLoading(button, false);
    }
}

function syncCurrentUserFromBackend(profile) {
    if (!profile) return;

    currentUser = {
        ...currentUser,
        name: profile.username || currentUser?.name || '',
        username: profile.username || currentUser?.username || '',
        email: profile.email || currentUser?.email || '',
        avatarBg: profile.avatar_bg_color || currentUser?.avatarBg || '#338A85',
        avatarImg: profile.avatar_image || currentUser?.avatarImg || '',
        language: "English (US)",
        region: "Philippines (GMT+8)",
        is_verified: !!profile.is_verified,
        morning_motivation_enabled: profile.morning_motivation_enabled !== false,
        evening_summary_enabled: profile.evening_summary_enabled !== false,
        device_notifications_enabled: !!profile.device_notifications_enabled
    };

    localStorage.setItem('vast_user', JSON.stringify(currentUser));
    updateProfileUI();
    populateSettingsInputs();
}

async function fetchUserProfile() {
    try {
        const response = await apiFetch(ENDPOINTS.profile, { method: 'GET' });
        if (!response.ok) return;

        const profile = await response.json();
        syncCurrentUserFromBackend(profile);
        return profile;
    } catch (err) {
        console.error('Failed to fetch user profile', err);
    }
}

let isOnline = false;
let currentUser = null;
let activeAuthMode = 'login';
let selectedAvatarFile = null;
let pendingVerificationUser = null;
let pendingPasswordReset = null;
const DEFAULT_LANGUAGE = "English (US)";
const DEFAULT_REGION = "Philippines (GMT+8)";

// Dynamic Filter State
let currentFilter = 'all';

// Calendar defaults (initialize to today)
let todayDate = new Date();
let selectedCalendarDate = new Date();
let calendarYear = todayDate.getFullYear();
let calendarMonth = todayDate.getMonth(); // 0-indexed

// Local Storage fallback system - starting with cleanly emptied arrays
let localTasks = [];
let localNotifications = [];
let extraEmails = [];

// Dynamic presets settings
let selectedLang = DEFAULT_LANGUAGE;
let selectedRegion = DEFAULT_REGION;
let activeAvatarBg = "#E2E8F0";
let activeAvatarImage = "";

// Modal specific trackers
let taskToDeleteId = null;
let renderedTaskCache = {};
let calendarTasksCache = [];
let notificationWatcherStarted = false;

const languagesData = [
    { name: "English(US)", sub: "" },
    { name: "Tagalog (fil-PH)", sub: "" },
    { name: "Español", sub: "" },
    { name: "Français", sub: "" },
    { name: "日本語", sub: "" }
];

const regionsData = [
    { name: "en-US", sub: "United States" },
    { name: "fil-PH", sub: "Philippines" },
    { name: "en-GB", sub: "United Kingdom" },
    { name: "ja-JP", sub: "Japan" },
    { name: "es-ES", sub: "Spain" }
];

function getTaskCategoryName(task) {
    return (task.category_name || task.category_label || 'Others').toString();
}

function getTaskCategoryClass(task) {
    const normalized = getTaskCategoryName(task).trim().toLowerCase();
    if (['school', 'work', 'personal'].includes(normalized)) {
        return `category-${normalized}`;
    }
    return 'category-others';
}

// Cache elements
const mainHeader = document.getElementById('mainHeader');
const authPageWrapper = document.getElementById('auth-page-wrapper');
const appContentWrapper = document.getElementById('app-content-wrapper');
const dashboardPanel = document.getElementById('dashboard-panel');
const calendarPanel = document.getElementById('calendar-panel');

const bellBtn = document.getElementById('bellBtn');
const profileBtn = document.getElementById('profileBtn');
const notifDropdown = document.getElementById('notifDropdown');
const profileDropdown = document.getElementById('profileDropdown');

const taskModal = document.getElementById('taskModal');
const openModalBtn = document.getElementById('openModalBtn');
const closeModalBtn = document.getElementById('closeModalBtn');
const taskForm = document.getElementById('taskForm');

const micBtn = document.getElementById('micBtn');
const voiceToast = document.getElementById('voiceToast');
const systemAlert = document.getElementById('systemAlert');
const authError = document.getElementById('authError');

// Application Startup Initialization
document.addEventListener('DOMContentLoaded', async () => {
    initializeDatabase();
    await checkBackendHandshake();
    await checkUserSession();
    handlePasswordResetLinkFromUrl();
    
    // Set default date input value to today
    document.getElementById('taskDate').value = getTodayDateString();
    document.getElementById('taskTime').value = "09:00";
    document.getElementById('taskCategory').value = "Others";
    
    initVoiceRecognition();
    initAIActions();
    initDeleteConfirmationListener();
    initCalendarControls();
    startTodayWatcher();
    startNotificationWatcher();
});

// Watch the system date and update `todayDate` when the day changes.
function startTodayWatcher() {
    // Check every 30 seconds whether the date rolled over
    setInterval(() => {
        const now = new Date();
        if (now.getFullYear() !== todayDate.getFullYear() || now.getMonth() !== todayDate.getMonth() || now.getDate() !== todayDate.getDate()) {
            todayDate = now;
            // Re-render to update the 'today' highlight
            if (calendarPanel && calendarPanel.classList.contains('active')) {
                renderCalendarMatrix();
                inspectCalendarSelectedDayTasks();
            } else {
                renderCalendarMatrix();
            }
        }
    }, 30000);
}

// Populate month/year dropdowns and wire events
function initCalendarControls() {
    const monthSelect = document.getElementById('calendarMonthSelect');
    const yearSelect = document.getElementById('calendarYearSelect');
    if (!monthSelect || !yearSelect) return;

    const monthNames = [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December"
    ];

    monthSelect.innerHTML = '';
    monthNames.forEach((m, i) => {
        const opt = document.createElement('option');
        opt.value = i;
        opt.textContent = m;
        monthSelect.appendChild(opt);
    });

    // Year range: current year -5 .. current year +5
    yearSelect.innerHTML = '';
    const current = todayDate.getFullYear();
    for (let y = current - 5; y <= current + 5; y++) {
        const opt = document.createElement('option');
        opt.value = y;
        opt.textContent = y;
        yearSelect.appendChild(opt);
    }

    monthSelect.value = calendarMonth;
    yearSelect.value = calendarYear;

    monthSelect.addEventListener('change', (e) => {
        calendarMonth = parseInt(e.target.value, 10);
        // keep selected day if possible, otherwise set to 1
        const day = Math.min(selectedCalendarDate.getDate(), new Date(calendarYear, calendarMonth + 1, 0).getDate());
        selectedCalendarDate = new Date(calendarYear, calendarMonth, day);
        renderCalendarMatrix();
        inspectCalendarSelectedDayTasks();
    });

    yearSelect.addEventListener('change', (e) => {
        calendarYear = parseInt(e.target.value, 10);
        const day = Math.min(selectedCalendarDate.getDate(), new Date(calendarYear, calendarMonth + 1, 0).getDate());
        selectedCalendarDate = new Date(calendarYear, calendarMonth, day);
        renderCalendarMatrix();
        inspectCalendarSelectedDayTasks();
    });
}

// --- AUTHENTICATION & SESSION HANDLING ---
async function checkUserSession() {
    const savedUser = localStorage.getItem('vast_user');
    if (savedUser) {
        currentUser = JSON.parse(savedUser);
        // Fetch fresh profile from server BEFORE updating UI to ensure latest data
        await fetchUserProfile();
        applySessionLogin(currentUser.username);
    } else {
        applySessionLogout();
    }
}

// Toggle Auth layout switch between sign-in and registration models
function toggleAuthMode() {
    clearAuthError();
    updatePasswordRequirements();
    const authSubmitBtn = document.getElementById('authSubmitBtn');
    const authToggleText = document.getElementById('authToggleText');
    const toggleAuthModeLink = document.getElementById('toggleAuthMode');
    
    if (activeAuthMode === 'login') {
        activeAuthMode = 'signup';
        authSubmitBtn.textContent = 'Register Account';
        authToggleText.textContent = 'Already have an account?';
        toggleAuthModeLink.textContent = 'Log In Here';
    } else {
        activeAuthMode = 'login';
        authSubmitBtn.textContent = 'Confirm Log In';
        authToggleText.textContent = "Don't have an account yet?";
        toggleAuthModeLink.textContent = 'Create an Account';
    }
}

// Handle confirmation of log in or user registration submitting form
async function handleAuthSubmit(event) {
    event.preventDefault();
    clearAuthError();
    const submitBtn = document.getElementById('authSubmitBtn');

    const emailInput = document.getElementById('authUsername').value.trim();
    const passwordInput = document.getElementById('authPassword').value;
    const fallbackName = emailInput.split('@')[0] || 'User';

    if (!emailInput) {
        setAuthError('Please enter your email.');
        return;
    }
    if (!passwordInput) {
        setAuthError('Please enter your password.');
        return;
    }
    if (activeAuthMode === 'signup' && !isStrongPassword(passwordInput)) {
        setAuthError('Please complete all password requirements.');
        return;
    }

    await withButtonLoading(submitBtn, async () => {
    try {
        const response = await apiFetch(activeAuthMode === 'signup' ? ENDPOINTS.register : ENDPOINTS.login, {
            method: 'POST',
            body: JSON.stringify({
                username: emailInput,
                password: passwordInput,
                email: emailInput
            })
        });

        if (!response.ok) {
            const errorBody = await response.json().catch(() => ({}));
            const errorMessage = formatApiError(errorBody) || 'Authentication failed. Please check your details.';
            if (errorBody.requires_verification) {
                pendingVerificationUser = {
                    email: errorBody.email || emailInput
                };
                openVerifyAccountModal();
            }
            setAuthError(errorMessage);
            showSystemToast(errorMessage);
            return;
        }

        const user = await response.json();
        currentUser = {
            username: user.username,
            name: user.username || fallbackName,
            email: user.email || emailInput,
            avatarBg: "#338A85",
            avatarImg: "",
            is_verified: !!user.is_verified,
            morning_motivation_enabled: true,
            evening_summary_enabled: true,
            device_notifications_enabled: false
        };
        isOnline = true;
        if (activeAuthMode === 'signup') {
            pendingVerificationUser = { email: user.email || emailInput };
            openVerifyAccountModal();
            const devCode = user.dev_verification_code ? ` Dev code: ${user.dev_verification_code}` : '';
            showSystemToast(`${user.message || 'Verification code sent. Please verify your account.'}${devCode}`);
            return;
        }
    } catch (err) {
        console.error("Backend auth unavailable, using local session fallback:", err);
        currentUser = {
            username: fallbackName,
            name: fallbackName,
            email: emailInput,
            avatarBg: "#338A85",
            avatarImg: "",
            is_verified: true,
            morning_motivation_enabled: true,
            evening_summary_enabled: true,
            device_notifications_enabled: false
        };
    }

    localStorage.setItem('vast_user', JSON.stringify(currentUser));
    
    // Vocal feedback validation speech synthesizer
    triggerVocalResponse(`Welcome to VAST, ${currentUser.name}! Speak your tasks or schedule manually.`);

    if (isOnline) {
        await fetchUserProfile();
    }

    applySessionLogin(currentUser.username);
    }, activeAuthMode === 'signup' ? 'Registering...' : 'Logging in...');
}

function applySessionLogin(username) {
    // Reset filter to default state on login
    currentFilter = 'all';
    
    // Un-render Auth page completely and reveal Dashboard Wrapper
    authPageWrapper.style.display = 'none';
    appContentWrapper.style.display = 'flex';
    
    // Apply profile updates
    updateProfileUI();

    navigateTo('dashboard');
    window.scrollTo(0, 0); // Reset page layout scroll position completely
}

function updateProfileUI() {
    if (!currentUser) return;
    
    const initials = currentUser.name.charAt(0).toUpperCase();
    
    // Update Text Nodes
    document.getElementById('profileName').textContent = currentUser.name;
    document.getElementById('avatarLetter').textContent = initials;
    document.getElementById('headerProfileAvatar').textContent = initials;
    document.getElementById('settingsSidebarAvatarLetter').textContent = initials;

    // Apply Presets (Image vs Color Backgrounds)
    const elements = [
        document.getElementById('avatarLetter'),
        document.getElementById('headerProfileAvatar'),
        document.getElementById('settingsSidebarAvatarLetter'),
        document.getElementById('avatarCirclePreview')
    ];

    elements.forEach(el => {
        if (el) {
            if (currentUser.avatarImg) {
                el.style.backgroundImage = `url(${currentUser.avatarImg})`;
                el.textContent = "";
            } else {
                el.style.backgroundImage = "none";
                el.textContent = initials;
                el.style.backgroundColor = currentUser.avatarBg || "#338A85";
                el.style.color = "white";
            }
        }
    });
}

async function handleLogout() {
    if (isOnline) {
        try {
            await apiFetch(ENDPOINTS.logout, { method: 'POST' });
        } catch (err) {
            console.warn('Backend logout failed; clearing local session only.', err);
        }
    }
    localStorage.removeItem('vast_user');
    currentUser = null;
    applySessionLogout();
    closeAllHeaderPopups();
}

function setAuthError(message) {
    if (authError) {
        authError.textContent = message;
    }
}

function clearAuthError() {
    if (authError) {
        authError.textContent = '';
    }
}

function togglePasswordVisibility(inputId, button) {
    const input = document.getElementById(inputId);
    if (!input) return;
    const show = input.type === 'password';
    input.type = show ? 'text' : 'password';
    if (button) {
        button.textContent = show ? '⌧' : '👁';
        button.setAttribute('aria-label', show ? 'Hide password' : 'Show password');
    }
}

function getPasswordRules(password) {
    return {
        length: password.length >= 8,
        upper: /[A-Z]/.test(password),
        lower: /[a-z]/.test(password),
        number: /\d/.test(password),
        special: /[^A-Za-z0-9]/.test(password)
    };
}

function isStrongPassword(password) {
    return Object.values(getPasswordRules(password)).every(Boolean);
}

function updatePasswordRequirements() {
    const checklist = document.getElementById('passwordChecklist');
    const password = document.getElementById('authPassword')?.value || '';
    if (!checklist) return;
    checklist.style.display = activeAuthMode === 'signup' ? 'grid' : 'none';
    const rules = getPasswordRules(password);
    checklist.querySelectorAll('li').forEach(item => {
        item.classList.toggle('valid', !!rules[item.dataset.rule]);
    });
}

function updateResetPasswordRequirements() {
    const checklist = document.getElementById('resetPasswordChecklist');
    const password = document.getElementById('resetNewPassword')?.value || '';
    if (!checklist) return;
    const rules = getPasswordRules(password);
    checklist.querySelectorAll('li').forEach(item => {
        item.classList.toggle('valid', !!rules[item.dataset.rule]);
    });
}

function showAuthPanel(panelId) {
    ['authForm', 'verificationPanel', 'passwordResetRequestPanel', 'passwordResetConfirmPanel'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.style.display = id === panelId ? 'block' : 'none';
    });
    const toggle = document.querySelector('.auth-toggle');
    if (toggle) toggle.style.display = panelId === 'authForm' ? 'block' : 'none';
}

function openPasswordResetRequest() {
    clearAuthError();
    const email = document.getElementById('authUsername')?.value.trim() || '';
    const resetEmail = document.getElementById('resetRequestEmail');
    if (appContentWrapper && appContentWrapper.style.display !== 'none') {
        appContentWrapper.style.display = 'none';
        authPageWrapper.style.display = 'flex';
    }
    if (resetEmail) resetEmail.value = email || currentUser?.email || '';
    showAuthPanel('passwordResetRequestPanel');
}

function closePasswordResetPanels() {
    pendingPasswordReset = null;
    showAuthPanel('authForm');
}

async function submitPasswordResetRequest() {
    const actionButton = typeof event !== 'undefined' ? event.target : null;
    const email = document.getElementById('resetRequestEmail')?.value.trim() || '';
    if (!email) {
        showSystemToast('Please enter your email.');
        return;
    }

    await withButtonLoading(actionButton, async () => {
    try {
        const response = await apiFetch(ENDPOINTS.passwordResetRequest, {
            method: 'POST',
            body: JSON.stringify({ email })
        });
        const body = await response.json().catch(() => ({}));
        if (!response.ok) {
            showSystemToast(`Password reset failed: ${formatApiError(body)}`);
            return;
        }
        if (body.dev_reset_url) {
            console.info('Development password reset URL:', body.dev_reset_url);
        }
        showSystemToast(body.detail || 'If an account exists, a reset link has been sent.');
        closePasswordResetPanels();
    } catch (err) {
        console.error('Password reset request failed', err);
        showSystemToast('Unable to send password reset email. Check connection.');
    }
    }, 'Sending...');
}

function handlePasswordResetLinkFromUrl() {
    const params = new URLSearchParams(window.location.search);
    const uid = params.get('reset_uid');
    const token = params.get('reset_token');
    if (!uid || !token) return;
    pendingPasswordReset = { uid, token };
    localStorage.removeItem('vast_user');
    currentUser = null;
    applySessionLogout();
    showAuthPanel('passwordResetConfirmPanel');
    const cleanUrl = `${window.location.origin}${window.location.pathname}`;
    window.history.replaceState({}, document.title, cleanUrl);
}

async function submitPasswordResetConfirm() {
    const actionButton = typeof event !== 'undefined' ? event.target : null;
    if (!pendingPasswordReset) {
        showSystemToast('Password reset link is missing or invalid.');
        return;
    }
    const newPassword = document.getElementById('resetNewPassword')?.value || '';
    const confirmPassword = document.getElementById('resetConfirmPassword')?.value || '';
    if (!isStrongPassword(newPassword)) {
        showSystemToast('Please complete all password requirements.');
        return;
    }
    if (newPassword !== confirmPassword) {
        showSystemToast('Passwords do not match.');
        return;
    }

    await withButtonLoading(actionButton, async () => {
    try {
        const response = await apiFetch(ENDPOINTS.passwordResetConfirm, {
            method: 'POST',
            body: JSON.stringify({
                uid: pendingPasswordReset.uid,
                token: pendingPasswordReset.token,
                new_password: newPassword
            })
        });
        const body = await response.json().catch(() => ({}));
        if (!response.ok) {
            showSystemToast(`Password reset failed: ${formatApiError(body)}`);
            return;
        }
        pendingPasswordReset = null;
        document.getElementById('resetNewPassword').value = '';
        document.getElementById('resetConfirmPassword').value = '';
        updateResetPasswordRequirements();
        showAuthPanel('authForm');
        showSystemToast(body.detail || 'Password has been reset successfully.');
    } catch (err) {
        console.error('Password reset confirm failed', err);
        showSystemToast('Unable to reset password. Check connection.');
    }
    }, 'Updating...');
}

function applySessionLogout() {
    // Hide dashboard framework completely and reveal clean Fullscreen Centered Auth page
    appContentWrapper.style.display = 'none';
    authPageWrapper.style.display = 'flex';
    
    dashboardPanel.classList.remove('active');
    calendarPanel.classList.remove('active');
    document.getElementById('settings-panel').classList.remove('active');
    window.scrollTo(0, 0); // Reset page layout scroll position completely
}

// --- LOCAL STORAGE DATABASE INITS (Empty by default) ---
function initializeDatabase() {
    if (!localStorage.getItem('vast_tasks')) {
        localStorage.setItem('vast_tasks', JSON.stringify([]));
    }
    if (!localStorage.getItem('vast_notifs')) {
        localStorage.setItem('vast_notifs', JSON.stringify([]));
    }
    if (!localStorage.getItem('vast_emails')) {
        localStorage.setItem('vast_emails', JSON.stringify([]));
    }
    localTasks = JSON.parse(localStorage.getItem('vast_tasks'));
    localNotifications = JSON.parse(localStorage.getItem('vast_notifs'));
    extraEmails = JSON.parse(localStorage.getItem('vast_emails'));
}

// --- DUAL-MODE HANDSHAKE MONITOR ---
async function checkBackendHandshake() {
    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 2000); // 2s quick probe
        
        const response = await apiFetch(ENDPOINTS.summary, { signal: controller.signal });
        clearTimeout(timeoutId);
        
        isOnline = !!(response && response.ok);
    } catch (err) {
        isOnline = false;
    }
}

// --- DASHBOARD DISPLAY SYSTEM ---
async function fetchDashboardData() {
    // Live backend versus Offline local execution switch
    if (isOnline) {
        try {
            const [summaryRes, todayRes, upcomingRes, allTasksRes] = await Promise.all([
                apiFetch(ENDPOINTS.summary),
                apiFetch(ENDPOINTS.today),
                apiFetch(ENDPOINTS.upcoming),
                apiFetch(ENDPOINTS.tasks)
            ]);

            if (summaryRes.ok) {
                const summary = await summaryRes.json();
                updateMetricsSummary(summary);
            }
            
            let todayTasks = [];
            let upcomingTasks = [];
            if (todayRes.ok) todayTasks = await todayRes.json();
            if (upcomingRes.ok) upcomingTasks = await upcomingRes.json();
            if (allTasksRes.ok) {
                calendarTasksCache = await allTasksRes.json();
                calendarTasksCache.forEach(task => {
                    renderedTaskCache[task.id] = task;
                });
            }

            // Apply unified filtering & render
            filterAndRenderDashboard(todayTasks, upcomingTasks);
        } catch (err) {
            console.error("Backend pipeline interrupted, returning to Offline Handshake execution...", err);
            isOnline = false;
            fetchDashboardDataOffline();
        }
    } else {
        fetchDashboardDataOffline();
    }
}

function fetchDashboardDataOffline() {
    // Calculate Offline Summary Statistics
    const todayStr = getTodayDateString();

    const pending = localTasks.filter(t => t.status !== 'completed').length;
    const completed = localTasks.filter(t => t.status === 'completed').length;
    const priority = localTasks.filter(t => t.priority === 'high' && t.status !== 'completed').length;
    
    // Check overdue task constraints
    const overdue = localTasks.filter(t => {
        return t.status !== 'completed' && t.date < todayStr;
    }).length;

    updateMetricsSummary({ pending, completed, priority, overdue });

    // Segment database normally based on May 17, 2026 timeline constraints
    const todayTasks = localTasks.filter(t => t.date === todayStr);
    const upcomingTasks = localTasks.filter(t => t.date > todayStr);

    filterAndRenderDashboard(todayTasks, upcomingTasks);
}

// --- UNIFIED FILTER RENDERING ENGINE ---
function filterAndRenderDashboard(allTodayTasks, allUpcomingTasks) {
    const todayStr = getTodayDateString();
    const sourceList = isOnline ? calendarTasksCache : localTasks;

    const todayTasks = sourceList.filter(t => t.date === todayStr);
    const upcomingTasks = sourceList.filter(t => t.date > todayStr);
    const overdueTasks = sourceList.filter(t => t.date < todayStr);

    let filteredToday = [...todayTasks];
    let filteredUpcoming = [...upcomingTasks];
    let todayLabel = "Today's Tasks";
    let upcomingLabel = "Upcoming Tasks";

    if (currentFilter === 'overdue') {
        filteredToday = overdueTasks.filter(t => t.status !== 'completed');
        filteredUpcoming = [];
        
        todayLabel = "Overdue Tasks";
        upcomingLabel = "";
    } else if (currentFilter !== 'all') {
        if (currentFilter === 'pending') {
            filteredToday = [...todayTasks, ...overdueTasks].filter(t => t.status !== 'completed');
            filteredUpcoming = upcomingTasks.filter(t => t.status !== 'completed');
        } else if (currentFilter === 'completed') {
            filteredToday = [...todayTasks, ...overdueTasks].filter(t => t.status === 'completed');
            filteredUpcoming = upcomingTasks.filter(t => t.status === 'completed');
        } else if (currentFilter === 'high') {
            filteredToday = [...todayTasks, ...overdueTasks].filter(t => t.priority === 'high' && t.status !== 'completed');
            filteredUpcoming = upcomingTasks.filter(t => t.priority === 'high' && t.status !== 'completed');
        }
    }

    // If a filter is active, switch to a single combined filtered view
    const tasksLayout = document.querySelector('.tasks-layout');
    const columns = tasksLayout ? tasksLayout.querySelectorAll(':scope > div') : [];

    if (currentFilter !== 'all') {
        const labelMap = { pending: 'In Progress', completed: 'Completed', high: 'Priority', overdue: 'Overdue' };
        const combined = [...filteredToday, ...filteredUpcoming];
        const headerLabel = labelMap[currentFilter] ? `${labelMap[currentFilter]} Tasks` : `${currentFilter.toUpperCase()} Tasks`;

        if (document.getElementById('todayHeaderLabel')) document.getElementById('todayHeaderLabel').textContent = headerLabel;
        if (document.getElementById('filterTextToday')) document.getElementById('filterTextToday').textContent = `(${currentFilter.toUpperCase()})`;
        if (document.getElementById('filterTextUpcoming')) document.getElementById('filterTextUpcoming').textContent = '';

        if (tasksLayout) tasksLayout.classList.add('filtered-mode');
        if (columns[1]) columns[1].style.display = 'none';

        renderTaskList(combined, 'today-tasks-list', false, true);
        if (document.getElementById('upcoming-tasks-list')) document.getElementById('upcoming-tasks-list').innerHTML = '';
    } else {
        // restore normal two-column layout
        // In default view, hide completed tasks and only show pending/in-progress tasks
        const visibleToday = filteredToday.filter(t => t.status !== 'completed');
        const visibleUpcoming = filteredUpcoming.filter(t => t.status !== 'completed');
        
        if (document.getElementById('todayHeaderLabel')) document.getElementById('todayHeaderLabel').textContent = todayLabel;
        if (document.getElementById('upcomingHeaderLabel')) document.getElementById('upcomingHeaderLabel').textContent = upcomingLabel;
        if (document.getElementById('filterTextToday')) document.getElementById('filterTextToday').textContent = '';
        if (document.getElementById('filterTextUpcoming')) document.getElementById('filterTextUpcoming').textContent = '';

        if (tasksLayout) tasksLayout.classList.remove('filtered-mode');
        if (columns[1]) columns[1].style.display = '';

        renderTaskList(visibleToday, 'today-tasks-list', true);
        renderTaskList(visibleUpcoming, 'upcoming-tasks-list', false);
    }
}

// --- DASHBOARD CARD METRICS UPDATE ACTION ---
function updateMetricsSummary(data) {
    document.getElementById('count-pending').textContent = data.pending ?? data.in_progress ?? 0;
    document.getElementById('count-completed').textContent = data.completed ?? 0;
    document.getElementById('count-priority').textContent = data.priority ?? 0;
    document.getElementById('count-overdue').textContent = data.overdue ?? 0;
}

function filterDashboardTasks(filterType) {
    if (currentFilter === filterType) {
        currentFilter = 'all'; // Toggle off
        showSystemToast("Clearing filters. Displaying all tasks.");
    } else {
        currentFilter = filterType;
        showSystemToast(`Filtering by: ${filterType.toUpperCase()}`);
    }

    const activeFilters = ['pending', 'completed', 'high', 'overdue'];
    const labels = ['pendings', 'completed', 'priority', 'overdue'];
    
    labels.forEach((lbl, index) => {
        const card = document.querySelector(`.stat-card.${lbl}`);
        if (activeFilters[index] === currentFilter) {
            card.style.transform = 'scale(1.04)';
            card.style.border = '2px solid var(--header-bg)';
        } else {
            card.style.transform = '';
            card.style.border = '';
        }
    });

    // Update filter sub-text dynamically
    const subLabel = currentFilter !== 'all' ? `(${currentFilter.toUpperCase()})` : '';
    document.getElementById('filterTextToday').textContent = subLabel;
    document.getElementById('filterTextUpcoming').textContent = subLabel;

    fetchDashboardData();
}

function renderTaskList(tasks, targetContainerId, isToday, forceShowDate = false) {
    const container = document.getElementById(targetContainerId);
    container.innerHTML = '';

    if (tasks.length === 0) {
        container.innerHTML = `<div class="no-tasks">No tasks found</div>`;
        return;
    }

    // Sort tasks by date then time chronologically
    tasks.sort((a, b) => {
        if (a.date === b.date) {
            return String(a.time || '').localeCompare(String(b.time || ''));
        }
        return String(a.date || '').localeCompare(String(b.date || ''));
    });

    tasks.forEach(task => {
        renderedTaskCache[task.id] = task;
        const taskItem = document.createElement('div');
        taskItem.className = `task-item ${getTaskCategoryClass(task)} ${task.status === 'completed' ? 'is-completed' : ''}`;
        
        const timeString = formatTime(task.time);
        const showFullDate = forceShowDate || !isToday;
        const displayMetadata = showFullDate ? `${formatShortDate(task.date)} • ${timeString}` : timeString;

        taskItem.innerHTML = `
            <div class="task-left">
                <input type="checkbox" class="task-checkbox" ${task.status === 'completed' ? 'checked' : ''} onchange="toggleTaskStatus(${task.id}, '${task.status}')">
                <span class="task-title">${escapeHTML(task.title)}</span>
            </div>
            <div class="task-right">
                <span class="task-time">${displayMetadata}</span>
                <div class="priority-dot ${task.priority}" title="${task.priority} priority"></div>
                <button class="reminder-task-btn" title="Reminder settings" onclick="openReminderModal(event, ${task.id})">&#128276;</button>
                <button class="edit-task-btn" title="Edit task" onclick="openEditTaskModal(event, ${task.id})">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 1 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg>
                </button>
                <button class="delete-task-btn" title="Delete task" onclick="deleteTask(${task.id})">&times;</button>
            </div>
        `;

        // Overdue badge: client-side check comparing combined date+time to now
        try {
            const now = new Date();
            let taskDateTime = null;
            if (task.time) {
                taskDateTime = new Date(`${task.date}T${task.time}`);
            } else if (task.date) {
                taskDateTime = new Date(`${task.date}T00:00:00`);
            }
            if (taskDateTime && task.status !== 'completed' && taskDateTime < now) {
                const rightCol = taskItem.querySelector('.task-right');
                const badge = document.createElement('span');
                badge.className = 'overdue-badge';
                badge.textContent = 'Overdue';
                rightCol.insertBefore(badge, rightCol.firstChild);
            }
        } catch (e) {
            // ignore client-side parse errors
        }

        container.appendChild(taskItem);
    });
}

// --- TASKS CRUCIAL OPERATION ENGINE ---
async function toggleTaskStatus(taskId, currentStatus) {
    const nextStatus = currentStatus === 'completed' ? 'pending' : 'completed';

    try {
        const response = await apiFetch(`${ENDPOINTS.tasks}${taskId}/`, {
            method: 'PATCH',
            body: JSON.stringify({ status: nextStatus })
        });
        if (response.ok) {
            isOnline = true;
            const task = renderedTaskCache[taskId] || {};
            fetchDashboardData();
            showSystemToast(nextStatus === 'completed' ? "Task marked complete." : "Task marked pending.");
            if (nextStatus === 'completed') {
                addSystemNotification("Congratulations!", `You've completed ${task.title || 'a task'}.`, formatNotificationTime(new Date()), "complete");
            }
            return;
        }
        const errorBody = await response.json().catch(() => ({}));
        showSystemToast(`Update failed: ${formatApiError(errorBody)}`);
    } catch (err) {
        console.error("Online patch mutation failure, transitioning offline:", err);
    }

    // Offline Handshake Fallback execution
    const taskIndex = localTasks.findIndex(t => t.id === taskId);
    if (taskIndex !== -1) {
        localTasks[taskIndex].status = nextStatus;
        saveLocalDatabase();
        
        if (nextStatus === 'completed') {
            showSystemToast(`Completed: ${localTasks[taskIndex].title}!`);
            addSystemNotification("Congratulations!", `You've completed ${localTasks[taskIndex].title}.`, "Just now", "complete");
        }
        
        fetchDashboardData();
        if (calendarPanel.classList.contains('active')) {
            renderCalendarMatrix();
            inspectCalendarSelectedDayTasks();
        }
    }
}

// Trigger custom styled delete confirmation modal
function deleteTask(taskId) {
    taskToDeleteId = taskId;
    const modal = document.getElementById('deleteConfirmModal');
    modal.classList.add('active');
}

function closeDeleteConfirmModal() {
    document.getElementById('deleteConfirmModal').classList.remove('active');
    taskToDeleteId = null;
}

function openReminderModal(event, taskId) {
    if (event) event.stopPropagation();
    const task = renderedTaskCache[taskId] || calendarTasksCache.find(t => t.id === taskId) || localTasks.find(t => t.id === taskId);
    const minutes = Number(task?.reminder_minutes_before ?? 10);
    const preset = document.getElementById('reminderPreset');
    document.getElementById('reminderTaskId').value = taskId;
    const presetValues = ['0', '5', '10', '30', '60', '1440', '10080'];
    preset.value = presetValues.includes(String(minutes)) ? String(minutes) : 'custom';
    document.getElementById('customReminderMinutes').value = minutes;
    document.getElementById('customReminderGroup').style.display = preset.value === 'custom' ? 'flex' : 'none';
    document.getElementById('reminderModal').classList.add('active');
}

function closeReminderModal() {
    document.getElementById('reminderModal').classList.remove('active');
}

document.addEventListener('change', (event) => {
    if (event.target && event.target.id === 'reminderPreset') {
        document.getElementById('customReminderGroup').style.display = event.target.value === 'custom' ? 'flex' : 'none';
    }
});

async function saveTaskReminder() {
    const taskId = parseInt(document.getElementById('reminderTaskId').value, 10);
    const preset = document.getElementById('reminderPreset').value;
    const minutes = preset === 'custom'
        ? parseInt(document.getElementById('customReminderMinutes').value || '10', 10)
        : parseInt(preset, 10);

    if (!Number.isFinite(minutes) || minutes < 0 || minutes > 43200) {
        showSystemToast('Choose a reminder from 0 minutes to 30 days before.');
        return;
    }

    try {
        const response = await apiFetch(`${ENDPOINTS.tasks}${taskId}/`, {
            method: 'PATCH',
            body: JSON.stringify({ reminder_minutes_before: minutes })
        });
        if (response.ok) {
            const task = await response.json();
            renderedTaskCache[task.id] = task;
            closeReminderModal();
            fetchDashboardData();
            showSystemToast(`Reminder set ${formatReminderOffset(minutes)}.`);
            return;
        }
        const body = await response.json().catch(() => ({}));
        showSystemToast(`Reminder update failed: ${formatApiError(body)}`);
    } catch (err) {
        const taskIndex = localTasks.findIndex(t => t.id === taskId);
        if (taskIndex !== -1) {
            localTasks[taskIndex].reminder_minutes_before = minutes;
            saveLocalDatabase();
            closeReminderModal();
            fetchDashboardData();
            showSystemToast(`Reminder set ${formatReminderOffset(minutes)}.`);
        }
    }
}

function initDeleteConfirmationListener() {
    document.getElementById('confirmDeleteBtn').addEventListener('click', async () => {
        if (!taskToDeleteId) return;
        const taskId = taskToDeleteId;
        closeDeleteConfirmModal();

        try {
            const response = await apiFetch(`${ENDPOINTS.tasks}${taskId}/`, {
                method: 'DELETE'
            });
            if (response.ok) {
                isOnline = true;
                fetchDashboardData();
                showSystemToast("Task deleted successfully.");
                return;
            }
            const errorBody = await response.json().catch(() => ({}));
            showSystemToast(`Delete failed: ${formatApiError(errorBody)}`);
            return;
        } catch (err) {
            console.error("Online delete process failure:", err);
        }

        // Offline Local Database fallback delete
        const taskIndex = localTasks.findIndex(t => t.id === taskId);
        if (taskIndex !== -1) {
            const deletedTitle = localTasks[taskIndex].title;
            localTasks.splice(taskIndex, 1);
            saveLocalDatabase();
            showSystemToast(`Deleted task: ${deletedTitle}`);
            
            fetchDashboardData();
            if (calendarPanel.classList.contains('active')) {
                renderCalendarMatrix();
                inspectCalendarSelectedDayTasks();
            }
        }
    });
}

// --- TASK EDITING & RETRIEVAL WORKFLOW ---
async function openEditTaskModal(event, taskId) {
    if (event) event.stopPropagation();

    let task = renderedTaskCache[taskId] || calendarTasksCache.find(t => t.id === taskId) || localTasks.find(t => t.id === taskId);

    if (!task) {
        try {
            const response = await fetch(`${ENDPOINTS.tasks}${taskId}/`);
            if (response.ok) {
                task = await response.json();
                renderedTaskCache[task.id] = task;
            }
        } catch (err) {
            console.error("Failed to fetch task for editing:", err);
        }
    }

    if (!task) {
        showSystemToast("Could not load this task for editing.");
        return;
    }

    document.getElementById('editTaskId').value = task.id;
    document.getElementById('editTaskTitle').value = task.title;
    document.getElementById('editTaskDate').value = task.date;
    document.getElementById('editTaskTime').value = normalizeTimeForInput(task.time);
    document.getElementById('editTaskPriority').value = task.priority;
    document.getElementById('editTaskCategory').value = task.category_name || 'Others';
    document.getElementById('editTaskStatus').value = task.status || 'pending';

    document.getElementById('editTaskModal').classList.add('active');
}

function closeEditTaskModal() {
    document.getElementById('editTaskModal').classList.remove('active');
}

async function handleEditTaskSubmit(event) {
    event.preventDefault();
    const submitButton = event.submitter;
    const taskId = parseInt(document.getElementById('editTaskId').value, 10);
    const title = document.getElementById('editTaskTitle').value.trim();
    const date = document.getElementById('editTaskDate').value;
    const time = document.getElementById('editTaskTime').value;
    const priority = document.getElementById('editTaskPriority').value;
    const category = document.getElementById('editTaskCategory').value;
    const status = document.getElementById('editTaskStatus').value;

    const payload = {
        title,
        date,
        time,
        priority,
        category_label: category,
        status
    };

    await withButtonLoading(submitButton, async () => {
    try {
        const response = await apiFetch(`${ENDPOINTS.tasks}${taskId}/`, {
            method: 'PATCH',
            body: JSON.stringify(payload)
        });
        if (response.ok) {
            isOnline = true;
            closeEditTaskModal();
            fetchDashboardData();
            showSystemToast("Task saved successfully!");
            return;
        }
        const errorBody = await response.json().catch(() => ({}));
        showSystemToast(`Edit failed: ${formatApiError(errorBody)}`);
    } catch (err) {
        console.error("Online task edit mutation failure:", err);
    }

    // Offline Local Database fallback update
    const taskIndex = localTasks.findIndex(t => t.id === taskId);
    if (taskIndex !== -1) {
        localTasks[taskIndex] = {
            ...localTasks[taskIndex],
            ...payload
        };
        saveLocalDatabase();
        closeEditTaskModal();
        showSystemToast(`Updated task: ${title}`);
        
        fetchDashboardData();
        if (calendarPanel.classList.contains('active')) {
            renderCalendarMatrix();
            inspectCalendarSelectedDayTasks();
        }
    }
    }, 'Saving...');
}

// --- MANUAL SUBMIT ENGINE ---
async function handleAddTaskSubmit(event) {
    event.preventDefault();
    const submitButton = event.submitter;
    const title = document.getElementById('taskTitle').value.trim();
    const date = document.getElementById('taskDate').value;
    const time = document.getElementById('taskTime').value;
    const priority = document.getElementById('taskPriority').value;
    const category = document.getElementById('taskCategory').value;

    const payload = {
        title,
        date,
        time,
        priority,
        category_label: category,
        reminder_minutes_before: 10,
        status: "pending"
    };

    await withButtonLoading(submitButton, async () => {
    try {
        const response = await apiFetch(ENDPOINTS.tasks, {
            method: 'POST',
            body: JSON.stringify(payload)
        });
        if (response.ok) {
            isOnline = true;
            finishTaskCreation();
            return;
        }
        const errorBody = await response.json().catch(() => ({}));
        showSystemToast(`Create failed: ${formatApiError(errorBody)}`);
    } catch (err) {
        console.error("Online task creation fallback executed:", err);
    }

    // Offline payload mock insertion
    const newTask = {
        id: Date.now(),
        ...payload
    };
    localTasks.push(newTask);
    saveLocalDatabase();
    finishTaskCreation();
    }, 'Saving...');
}

function finishTaskCreation() {
    taskForm.reset();
    // Default restore
    document.getElementById('taskDate').value = getTodayDateString();
    document.getElementById('taskTime').value = "09:00";
    
    toggleModal(false);
    fetchDashboardData();
    
    if (calendarPanel.classList.contains('active')) {
        renderCalendarMatrix();
        inspectCalendarSelectedDayTasks();
    }

    showSystemToast("Task successfully created!");
    triggerVocalResponse("Task successfully created.");
}

function saveLocalDatabase() {
    localStorage.setItem('vast_tasks', JSON.stringify(localTasks));
    localStorage.setItem('vast_notifs', JSON.stringify(localNotifications));
    localStorage.setItem('vast_emails', JSON.stringify(extraEmails));
}

// --- CALENDAR GRID IMPLEMENTATION ---
function renderCalendarMatrix() {
    const grid = document.getElementById('calendarGrid');
    grid.innerHTML = '';

    // Render Weekday Labels Sun-Sat
    const weekdays = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    weekdays.forEach(day => {
        const dayHeader = document.createElement('div');
        dayHeader.className = 'weekday-label';
        dayHeader.textContent = day;
        grid.appendChild(dayHeader);
    });

    // May 2026 starts on Friday (start day offset = 5)
    const daysInMonth = new Date(calendarYear, calendarMonth + 1, 0).getDate();
    const startDayOffset = new Date(calendarYear, calendarMonth, 1).getDay();

    // Populate empty calendar spaces
    for (let i = 0; i < startDayOffset; i++) {
        const emptyCell = document.createElement('div');
        emptyCell.className = 'cal-day empty-day';
        grid.appendChild(emptyCell);
    }

    // Draw month days
    for (let day = 1; day <= daysInMonth; day++) {
        const dayCell = document.createElement('div');
        dayCell.className = 'cal-day';
        dayCell.textContent = day;

        // Formulate verification date context
        const yearStr = calendarYear;
        const monthStr = String(calendarMonth + 1).padStart(2, '0');
        const dayStr = String(day).padStart(2, '0');
        const dateCompare = `${yearStr}-${monthStr}-${dayStr}`;

        // Mark date cell if active selected
        if (selectedCalendarDate.getDate() === day && 
            selectedCalendarDate.getMonth() === calendarMonth && 
            selectedCalendarDate.getFullYear() === calendarYear) {
            dayCell.classList.add('active-day');
        }

        // Highlight today's date
        if (todayDate.getDate() === day && todayDate.getMonth() === calendarMonth && todayDate.getFullYear() === calendarYear) {
            dayCell.classList.add('today');
        }

        // CHECK DYNAMIC TASK DOT: Circles below ONLY appear if tasks are scheduled for that specific day
        const calendarSourceTasks = isOnline ? calendarTasksCache : localTasks;
        const hasTasks = calendarSourceTasks.some(t => t.date === dateCompare);
        if (hasTasks) {
            dayCell.classList.add('has-tasks');
        }

        dayCell.addEventListener('click', () => {
            selectCalendarDate(day);
        });

        grid.appendChild(dayCell);
    }

    // Dynamic header label
    const monthNames = [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December"
    ];
    // If month/year selects exist, keep them in sync; otherwise update textual label
    const monthSelect = document.getElementById('calendarMonthSelect');
    const yearSelect = document.getElementById('calendarYearSelect');
    if (monthSelect && yearSelect) {
        monthSelect.value = calendarMonth;
        yearSelect.value = calendarYear;
        // update accessible textual label for screen readers if present
        const label = document.getElementById('calendarMonthLabel');
        if (label) label.textContent = `${monthNames[calendarMonth]} ${calendarYear}`;
    } else {
        const label = document.getElementById('calendarMonthLabel');
        if (label) label.textContent = `${monthNames[calendarMonth]} ${calendarYear}`;
    }
}

function changeMonth(dir) {
    calendarMonth += dir;
    if (calendarMonth < 0) {
        calendarMonth = 11;
        calendarYear--;
    } else if (calendarMonth > 11) {
        calendarMonth = 0;
        calendarYear++;
    }
    
    // Re-anchor active day boundary selection safety checks
    selectedCalendarDate = new Date(calendarYear, calendarMonth, 1);
    renderCalendarMatrix();
    inspectCalendarSelectedDayTasks();
}

function selectCalendarDate(day) {
    selectedCalendarDate = new Date(calendarYear, calendarMonth, day);
    renderCalendarMatrix();
    inspectCalendarSelectedDayTasks();
}

function inspectCalendarSelectedDayTasks() {
    const listContainer = document.getElementById('calendarDayTaskList');
    const dateLabel = document.getElementById('focusedDateLabel');

    const weekdayOptions = { weekday: 'short', month: 'short', day: 'numeric' };
    dateLabel.textContent = selectedCalendarDate.toLocaleDateString('en-US', weekdayOptions);

    const yearStr = selectedCalendarDate.getFullYear();
    const monthStr = String(selectedCalendarDate.getMonth() + 1).padStart(2, '0');
    const dayStr = String(selectedCalendarDate.getDate()).padStart(2, '0');
    const formattedDate = `${yearStr}-${monthStr}-${dayStr}`;

    // Filtering matches corresponding exactly to current date
    const calendarSourceTasks = isOnline ? calendarTasksCache : localTasks;
    const dayTasks = calendarSourceTasks.filter(t => t.date === formattedDate);

    listContainer.innerHTML = '';

    if (dayTasks.length === 0) {
        listContainer.innerHTML = `<div class="no-tasks">No tasks scheduled for this day</div>`;
        return;
    }

    dayTasks.sort((a, b) => a.time.localeCompare(b.time));

    dayTasks.forEach(task => {
        renderedTaskCache[task.id] = task;
        const taskCard = document.createElement('div');
        taskCard.className = `task-item ${getTaskCategoryClass(task)} ${task.status === 'completed' ? 'is-completed' : ''}`;
        
        taskCard.innerHTML = `
            <div class="task-left">
                <input type="checkbox" class="task-checkbox" ${task.status === 'completed' ? 'checked' : ''} onchange="toggleTaskStatus(${task.id}, '${task.status}')">
                <span class="task-title">${escapeHTML(task.title)}</span>
            </div>
            <div class="task-right">
                <span class="task-time">${formatTime(task.time)}</span>
                <div class="priority-dot ${task.priority}"></div>
                <button class="reminder-task-btn" title="Reminder settings" onclick="openReminderModal(event, ${task.id})">&#128276;</button>
                <button class="edit-task-btn" title="Edit task" onclick="openEditTaskModal(event, ${task.id})">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 1 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg>
                </button>
                <button class="delete-task-btn" title="Delete task" onclick="deleteTask(${task.id})">&times;</button>
            </div>
        `;
        listContainer.appendChild(taskCard);
    });
}

// --- ACCOUNT SETTINGS COMPONENT POPULATION ---
function populateSettingsInputs() {
    if (!currentUser) return;

    // Pre-populate sidebar branding
    const sidebarNameEl = document.getElementById('settingsSidebarName');
    if (sidebarNameEl) sidebarNameEl.textContent = currentUser.username || currentUser.name;

    // Populate username and email inputs
    const usernameEl = document.getElementById('settingsUsername');
    if (usernameEl) usernameEl.value = currentUser.username || '';
    const emailValue = currentUser.email || currentUser.username || '';
    const emailReadEl = document.getElementById('settingsEmailReadOnly');
    if (emailReadEl) emailReadEl.value = emailValue;
    const emailEl = document.getElementById('settingsEmail');
    if (emailEl) emailEl.value = emailValue;

    const deviceToggle = document.getElementById('deviceNotificationsToggle');
    if (deviceToggle) deviceToggle.checked = !!currentUser.device_notifications_enabled;

    // Render Extra Connected Emails dynamically if present
    renderExtraEmails();

    // Set active settings language/region badges
    document.getElementById('settingsActiveLangDesc').textContent = DEFAULT_LANGUAGE;
    document.getElementById('settingsActiveRegionDesc').textContent = DEFAULT_REGION;

    // Update photo previews
    const box = document.getElementById('settingsPicBox');
    if (currentUser.avatarImg) {
        box.style.backgroundImage = `url(${currentUser.avatarImg})`;
        box.innerHTML = '';
    } else {
        box.style.backgroundImage = 'none';
        box.style.backgroundColor = currentUser.avatarBg || '#F8F9FA';
        box.innerHTML = `<span style="font-size:32px; font-weight:700; color:white;">${currentUser.name.charAt(0).toUpperCase()}</span>`;
    }
}

function switchSettingsTab(tabName) {
    // Deactivate all panes
    document.querySelectorAll('.settings-content-pane').forEach(pane => pane.classList.remove('active'));
    document.querySelectorAll('.settings-nav-item').forEach(item => item.classList.remove('active'));

    // Activate chosen pane and sidebar item
    document.getElementById(`settings-pane-${tabName}`).classList.add('active');
    
    // Match click selectors
    const targetNavIndex = tabName === 'profile' ? 0 : tabName === 'password' ? 1 : tabName === 'language' ? 2 : 3;
    document.querySelectorAll('.settings-nav-item')[targetNavIndex].classList.add('active');
}

async function savePersonalDetails() {
    const username = document.getElementById('settingsUsername').value.trim();

    if (username.length < 3) {
        showSystemToast("Username must be at least 3 characters.");
        return;
    }

    if (isOnline) {
        try {
            const response = await apiFetch(ENDPOINTS.profile, {
                method: 'PATCH',
                body: JSON.stringify({ username })
            });

            if (response.ok) {
                const profile = await response.json();
                syncCurrentUserFromBackend(profile);
                showSystemToast("Username updated successfully.");
                triggerVocalResponse("Profile saved successfully.");
                return;
            }

            const errorBody = await response.json().catch(() => ({}));
            console.warn('Profile update failed', errorBody);
            const verifiedProfile = await fetchUserProfile();
            if (verifiedProfile?.username === username) {
                showSystemToast("Username updated successfully.");
                triggerVocalResponse("Profile saved successfully.");
                return;
            }
            showSystemToast(`Unable to save profile details: ${formatApiError(errorBody)}`);
            return;
        } catch (err) {
            console.error('Profile update error', err);
            const verifiedProfile = await fetchUserProfile();
            if (verifiedProfile?.username === username) {
                showSystemToast("Username updated successfully.");
                triggerVocalResponse("Profile saved successfully.");
                return;
            }
            showSystemToast("Unable to save profile details to the server. Saved locally.");
        }
    }

    currentUser.username = username;
    currentUser.name = username;
    localStorage.setItem('vast_user', JSON.stringify(currentUser));
    updateProfileUI();
    populateSettingsInputs();
    showSystemToast("Username updated locally.");
    triggerVocalResponse("Profile saved successfully.");
}

function focusUsernameEdit() {
    switchSettingsTab('profile');
    const input = document.getElementById('settingsUsername');
    if (input) {
        input.focus();
        input.select();
    }
}

async function saveNewPassword() {
    const currentPass = document.getElementById('settingsCurrentPassword').value;
    const newPass = document.getElementById('settingsNewPassword').value;
    const confirmPass = document.getElementById('settingsRetypePassword').value;

    if (!currentPass || !newPass) {
        showSystemToast("All password form groups are required.");
        return;
    }

    if (newPass !== confirmPass) {
        showSystemToast("Passwords mismatch! Retype confirmation.");
        return;
    }

    if (!isStrongPassword(newPass)) {
        showSystemToast("New password must meet the strong password requirements.");
        return;
    }

    if (isOnline) {
        try {
            const response = await apiFetch(`${API_BASE}/accounts/change-password/`, {
                method: 'POST',
                body: JSON.stringify({
                    current_password: currentPass,
                    new_password: newPass
                })
            });

            if (response.ok) {
                showSystemToast("Password changed successfully!");
                triggerVocalResponse("Password updated securely.");
                document.getElementById('settingsCurrentPassword').value = '';
                document.getElementById('settingsNewPassword').value = '';
                document.getElementById('settingsRetypePassword').value = '';
                return;
            }

            const errorBody = await response.json().catch(() => ({}));
            const errorMsg = errorBody.current_password?.[0] || errorBody.new_password?.[0] || 'Failed to change password';
            showSystemToast(errorMsg);
        } catch (err) {
            console.error('Password change error', err);
            showSystemToast("Unable to change password. Please try again.");
        }
    } else {
        showSystemToast("You are offline. Please connect to save password changes.");
    }
}

// --- NOTIFICATION SETTINGS HANDLERS ---
async function saveNotificationSettings() {
    const toggle = document.getElementById('deviceNotificationsToggle');
    let enabled = !!toggle?.checked;

    if (enabled && 'Notification' in window && Notification.permission === 'default') {
        const permission = await Notification.requestPermission();
        if (permission !== 'granted') {
            if (toggle) toggle.checked = false;
            enabled = false;
            showSystemToast('Device notifications were not allowed by the browser.');
            return;
        }
    }

    if (enabled && 'Notification' in window && Notification.permission !== 'granted') {
        if (toggle) toggle.checked = false;
        enabled = false;
        showSystemToast('Device notifications are blocked in this browser.');
        return;
    }

    currentUser.device_notifications_enabled = enabled;
    localStorage.setItem('vast_user', JSON.stringify(currentUser));

    if (!isOnline) {
        showSystemToast('Notification preference saved on this browser.');
        return;
    }

    try {
        const resp = await apiFetch(ENDPOINTS.profile, {
            method: 'PATCH',
            body: JSON.stringify({ device_notifications_enabled: enabled })
        });

        if (resp.ok) {
            const profile = await resp.json();
            syncCurrentUserFromBackend(profile);
            showSystemToast('Notification settings saved.');
            return;
        }

        const body = await resp.json().catch(() => ({}));
        console.warn('Save notification settings failed', body);
        showSystemToast('Notification preference saved on this browser.');
    } catch (err) {
        console.error('Save notification settings failed', err);
        showSystemToast('Notification preference saved on this browser.');
    }
}
async function saveEmailChanges() {
    const newEmail = document.getElementById('settingsEmail').value.trim();

    if (!newEmail) {
        showSystemToast("Please enter an email address.");
        return;
    }

    // Basic email validation
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(newEmail)) {
        showSystemToast("Please enter a valid email address.");
        return;
    }

    if (isOnline) {
        try {
            const response = await apiFetch(ENDPOINTS.profile, {
                method: 'PATCH',
                body: JSON.stringify({
                    email: newEmail
                })
            });

            if (response.ok) {
                const profile = await response.json();
                currentUser.email = profile.email;
                localStorage.setItem('vast_user', JSON.stringify(currentUser));
                showSystemToast("Email updated successfully!");
                triggerVocalResponse("Email address updated.");
                return;
            }

            const errorBody = await response.json().catch(() => ({}));
            showSystemToast("Unable to update email. Please try again.");
        } catch (err) {
            console.error('Email change error', err);
            showSystemToast("Unable to update email. Please try again.");
        }
    } else {
        showSystemToast("You are offline. Please connect to save email changes.");
    }
}

// --- POPUP MODAL CONTROL ENGINE (NEW Figma Assets) ---

// 1. Upload Photo Modal (`Upload photo.png`)
function openUploadPhotoModal() {
    const modal = document.getElementById('uploadPhotoModal');
    modal.classList.add('active');
    
    // Sync active preview color
    activeAvatarBg = currentUser.avatarBg || "#E2E8F0";
    activeAvatarImage = currentUser.avatarImg || "";
    
    updateAvatarPreviewInModal();
    
    // Select active preset border
    document.querySelectorAll('.avatar-preset-btn').forEach(btn => {
        const btnColor = rgb2hex(btn.style.backgroundColor).toUpperCase();
        const activeHex = activeAvatarBg.toUpperCase();
        if (btnColor === activeHex) {
            btn.classList.add('selected');
        } else {
            btn.classList.remove('selected');
        }
    });
}

function closeUploadPhotoModal() {
    document.getElementById('uploadPhotoModal').classList.remove('active');
}

function selectAvatarPreset(colorHex, imgBase64 = "") {
    selectedAvatarFile = null;
    activeAvatarBg = colorHex;
    activeAvatarImage = imgBase64;
    
    // Highlight selected
    document.querySelectorAll('.avatar-preset-btn').forEach(btn => {
        const btnColor = rgb2hex(btn.style.backgroundColor).toUpperCase();
        if (btnColor === colorHex.toUpperCase()) {
            btn.classList.add('selected');
        } else {
            btn.classList.remove('selected');
        }
    });
    
    updateAvatarPreviewInModal();
}

function handlePhotoFileSelected(event) {
    const file = event.target.files[0];
    if (!file) return;
    selectedAvatarFile = file;
    
    const reader = new FileReader();
    reader.onload = function(e) {
        activeAvatarImage = e.target.result;
        activeAvatarBg = ""; // Reset background color to prefer image
        updateAvatarPreviewInModal();
    };
    reader.readAsDataURL(file);
}

function updateAvatarPreviewInModal() {
    const preview = document.getElementById('avatarCirclePreview');
    const initials = currentUser ? currentUser.name.charAt(0).toUpperCase() : "J";
    
    if (activeAvatarImage) {
        preview.style.backgroundImage = `url(${activeAvatarImage})`;
        preview.textContent = "";
    } else {
        preview.style.backgroundImage = "none";
        preview.style.backgroundColor = activeAvatarBg;
        preview.style.color = "white";
        preview.textContent = initials;
    }
}

async function saveUploadPhoto() {
    const formData = new FormData();
    formData.append('avatar_bg_color', activeAvatarBg || currentUser?.avatarBg || '#338A85');

    if (selectedAvatarFile) {
        formData.append('avatar_image', selectedAvatarFile);
    } else if (!activeAvatarImage) {
        formData.append('avatar_image', '');
    }

    if (isOnline) {
        try {
            const response = await apiFetchForm(ENDPOINTS.profile, formData, { method: 'PATCH' });
            if (response.ok) {
                const profile = await response.json();
                syncCurrentUserFromBackend(profile);
                closeUploadPhotoModal();
                showSystemToast("Avatar profile picture updated successfully!");
                return;
            }

            const errorBody = await response.json().catch(() => ({}));
            console.warn('Avatar save failed', errorBody);
            const verifiedProfile = await fetchUserProfile();
            const savedColor = verifiedProfile?.avatar_bg_color === (activeAvatarBg || currentUser?.avatarBg || '#338A85');
            const savedImage = !!selectedAvatarFile && !!verifiedProfile?.avatar_image;
            if (savedColor || savedImage) {
                closeUploadPhotoModal();
                showSystemToast("Avatar profile picture updated successfully!");
                return;
            }
            showSystemToast(`Unable to save avatar: ${formatApiError(errorBody)}`);
            return;
        } catch (err) {
            console.error('Avatar save error', err);
            const verifiedProfile = await fetchUserProfile();
            const savedColor = verifiedProfile?.avatar_bg_color === (activeAvatarBg || currentUser?.avatarBg || '#338A85');
            const savedImage = !!selectedAvatarFile && !!verifiedProfile?.avatar_image;
            if (savedColor || savedImage) {
                closeUploadPhotoModal();
                showSystemToast("Avatar profile picture updated successfully!");
                return;
            }
            showSystemToast("Unable to save avatar to the server. Saved locally.");
        }
    }

    currentUser.avatarBg = activeAvatarBg;
    currentUser.avatarImg = activeAvatarImage;
    localStorage.setItem('vast_user', JSON.stringify(currentUser));
    updateProfileUI();
    populateSettingsInputs();
    closeUploadPhotoModal();
    showSystemToast("Avatar profile picture updated successfully!");
}

// Helper: Convert RGB background back to Hex for comparison matches
function rgb2hex(rgb) {
    if (/^#[0-9A-F]{6}$/i.test(rgb)) return rgb;
    rgb = rgb.match(/^rgb\((\d+),\s*(\d+),\s*(\d+)\)$/);
    function hex(x) {
        return ("0" + parseInt(x).toString(16)).slice(-2);
    }
    return rgb ? "#" + hex(rgb[1]) + hex(rgb[2]) + hex(rgb[3]) : rgb;
}

// Render connected emails dynamically
function renderExtraEmails() {
    const container = document.getElementById('additionalEmailsContainer');
    container.innerHTML = '';
    
    extraEmails.forEach((em, index) => {
        const group = document.createElement('div');
        group.className = 'auth-form-group';
        group.style.marginTop = '10px';
        group.innerHTML = `
            <label>Secondary Account #${index + 1}</label>
            <div style="display:flex; gap:8px; align-items:center;">
                <input type="email" class="auth-input" value="${em}" readonly style="margin-bottom:0; flex-grow:1;">
                <button class="delete-task-btn" style="background:#FEE2E2; color:#B91C1C; height:44px; width:44px; border-radius:12px;" onclick="removeSecondaryEmail(${index})">&times;</button>
            </div>
        `;
        container.appendChild(group);
    });
}

function removeSecondaryEmail(index) {
    const removed = extraEmails.splice(index, 1);
    saveLocalDatabase();
    renderExtraEmails();
    showSystemToast(`Removed secondary account: ${removed}`);
}

function openVerifyAccountModal(userData = null) {
    if (userData) pendingVerificationUser = userData;
    showAuthPanel('verificationPanel');
    const input = document.getElementById('verifyAccountCode');
    if (input) {
        input.value = '';
        input.focus();
    }
}

function closeVerifyAccountModal() {
    showAuthPanel('authForm');
    const input = document.getElementById('verifyAccountCode');
    if (input) input.value = '';
}

async function submitAccountVerification() {
    const code = document.getElementById('verifyAccountCode')?.value.trim() || '';
    if (!pendingVerificationUser || !code) {
        showSystemToast('Please enter the verification code.');
        return;
    }

    try {
        const response = await apiFetch(ENDPOINTS.verifyAccount, {
            method: 'POST',
            body: JSON.stringify({
                email: pendingVerificationUser.email,
                code
            })
        });

        if (!response.ok) {
            const body = await response.json().catch(() => ({}));
            showSystemToast(`Verification failed: ${formatApiError(body)}`);
            return;
        }

        closeVerifyAccountModal();
        showSystemToast('Account verified successfully.');
        const verified = await response.json().catch(() => ({}));
        currentUser = {
            username: verified.username,
            name: verified.username,
            email: verified.email || pendingVerificationUser.email,
            avatarBg: "#338A85",
            avatarImg: "",
            is_verified: true,
            morning_motivation_enabled: true,
            evening_summary_enabled: true,
            language: DEFAULT_LANGUAGE,
            region: DEFAULT_REGION
        };
        localStorage.setItem('vast_user', JSON.stringify(currentUser));
        await fetchUserProfile();
        applySessionLogin(currentUser.username);
    } catch (err) {
        console.error('Account verification error', err);
        showSystemToast('Unable to verify account. Check connection.');
    }
}

// Secure Change Email modal handlers
function openChangeEmailModal() {
    document.getElementById('changeEmailModal').classList.add('active');
}
function closeChangeEmailModal() {
    document.getElementById('changeEmailModal').classList.remove('active');
    document.getElementById('changeEmailNew').value = '';
    document.getElementById('changeEmailPassword').value = '';
}

async function submitChangeEmail() {
    const newEmail = document.getElementById('changeEmailNew').value.trim();
    const password = document.getElementById('changeEmailPassword').value;
    if (!newEmail || !password) { showSystemToast('Please provide new email and password.'); return; }
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(newEmail)) { showSystemToast('Invalid email format.'); return; }

    try {
        const response = await apiFetch(ENDPOINTS.changeEmail, {
            method: 'POST',
            body: JSON.stringify({ new_email: newEmail, password })
        });
        if (response.ok) {
            const payload = await response.json().catch(() => ({}));
            closeChangeEmailModal();
            pendingVerificationUser = {
                username: currentUser?.username || '',
                email: newEmail
            };
            openVerifyAccountModal();
            const devCode = payload.dev_verification_code ? ` Dev code: ${payload.dev_verification_code}` : '';
            showSystemToast(`Email change requested. Please verify the new email via verification code.${devCode}`);
            fetchUserProfile();
            return;
        }
        const body = await response.json().catch(() => ({}));
        showSystemToast(`Change email failed: ${formatApiError(body)}`);
    } catch (err) {
        console.error('Change email error', err);
        showSystemToast('Unable to change email. Check connection.');
    }
}

// Secure Delete Account modal handlers
function openDeleteAccountModal() {
    document.getElementById('deleteAccountModal').classList.add('active');
}
function closeDeleteAccountModal() {
    document.getElementById('deleteAccountModal').classList.remove('active');
    const p = document.getElementById('deleteAccountPassword'); if (p) p.value = '';
}

async function submitDeleteAccount() {
    const password = document.getElementById('deleteAccountPassword').value;
    if (!password) { showSystemToast('Please enter your password to confirm deletion.'); return; }

    try {
        const response = await apiFetch(ENDPOINTS.deleteAccount, {
            method: 'POST',
            body: JSON.stringify({ password })
        });
        if (response.ok) {
            closeDeleteAccountModal();
            localStorage.clear();
            currentUser = null;
            applySessionLogout();
            showSystemToast('Your account has been permanently deleted.');
            return;
        }
        const body = await response.json().catch(() => ({}));
        showSystemToast(`Account deletion failed: ${formatApiError(body)}`);
    } catch (err) {
        console.error('Account deletion error', err);
        showSystemToast('Unable to delete account. Please try again later.');
    }
}

// 3. Language Selection Modal (`Select language.png`)
function openLanguageModal() {
    document.getElementById('languageModal').classList.add('active');
    document.getElementById('langSearchInput').value = '';
    renderLanguagesList(languagesData);
}

function closeLanguageModal() {
    document.getElementById('languageModal').classList.remove('active');
}

function renderLanguagesList(dataList) {
    const container = document.getElementById('languageListContainer');
    container.innerHTML = '';
    
    dataList.forEach(item => {
        const isSelected = item.name === selectedLang;
        const div = document.createElement('div');
        div.className = `popup-list-item ${isSelected ? 'selected' : ''}`;
        div.onclick = () => {
            selectAppLanguage(item.name);
        };
        
        div.innerHTML = `
            <div>
                <h4 style="font-size:14px; font-weight:600; color:var(--text-main);">${item.name}</h4>
                ${item.sub ? `<p style="font-size:11px; color:var(--text-muted); margin-top:2px;">${item.sub}</p>` : ''}
            </div>
            <div class="popup-radio-dot"></div>
        `;
        container.appendChild(div);
    });
}

// Filter language matches dynamically
function filterLanguages() {
    const q = document.getElementById('langSearchInput').value.toLowerCase();
    const filtered = languagesData.filter(l => 
        l.name.toLowerCase().includes(q) || (l.sub && l.sub.toLowerCase().includes(q))
    );
    renderLanguagesList(filtered);
}

// 4. Region Selection Modal (`Region and format.png`)
function openRegionModal() {
    document.getElementById('regionModal').classList.add('active');
    document.getElementById('regionSearchInput').value = '';
    renderRegionsList(regionsData);
}

function closeRegionModal() {
    document.getElementById('regionModal').classList.remove('active');
}

function renderRegionsList(dataList) {
    const container = document.getElementById('regionListContainer');
    container.innerHTML = '';
    
    dataList.forEach(item => {
        const isSelected = item.name === selectedRegion;
        const div = document.createElement('div');
        div.className = `popup-list-item ${isSelected ? 'selected' : ''}`;
        div.onclick = () => {
            selectAppRegion(item.name);
        };
        
        div.innerHTML = `
            <div>
                <h4 style="font-size:14px; font-weight:600; color:var(--text-main);">${item.name}</h4>
                <p style="font-size:11px; color:var(--text-muted); margin-top:2px;">${item.sub}</p>
            </div>
            <div class="popup-radio-dot"></div>
        `;
        container.appendChild(div);
    });
}

function selectAppRegion(regionName) {
    selectedRegion = regionName;
    populateSettingsInputs();
    closeRegionModal();
    showSystemToast(`Region format calibrated to: ${regionName}`);
}

// Filter regions dynamically
function filterRegions() {
    const q = document.getElementById('regionSearchInput').value.toLowerCase();
    const filtered = regionsData.filter(r => 
        r.name.toLowerCase().includes(q) || r.sub.toLowerCase().includes(q)
    );
    renderRegionsList(filtered);
}

// --- OVERLAYS AND HEADER ACTIONS ---
function closeAllHeaderPopups() {
    notifDropdown.classList.remove('open');
    profileDropdown.classList.remove('open');
    bellBtn.classList.remove('active-badge');
    profileBtn.classList.remove('active-badge');
}

bellBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    const isOpen = notifDropdown.classList.toggle('open');
    profileDropdown.classList.remove('open');
    profileBtn.classList.remove('active-badge');
    bellBtn.classList.toggle('active-badge', isOpen);
    if (isOpen) renderNotifications();
});

profileBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    const isOpen = profileDropdown.classList.toggle('open');
    notifDropdown.classList.remove('open');
    bellBtn.classList.remove('active-badge');
    profileBtn.classList.toggle('active-badge', isOpen);
});

document.addEventListener('click', () => {
    closeAllHeaderPopups();
});

// Prevention inside popup propagation bounds
notifDropdown.addEventListener('click', (e) => e.stopPropagation());
profileDropdown.addEventListener('click', (e) => e.stopPropagation());

function renderNotifications() {
    const container = document.getElementById('notifList');
    container.innerHTML = '';
    
    if (localNotifications.length === 0) {
        container.innerHTML = '<div class="no-tasks" style="padding: 20px 0;">No new notifications</div>';
        document.getElementById('notifBadge').style.display = 'none';
        return;
    }

    document.getElementById('notifBadge').style.display = 'block';

    localNotifications.forEach(notif => {
        const item = document.createElement('div');
        item.className = `notif-item ${notif.type || ''}`;
        item.innerHTML = `
            <div class="notif-title">${escapeHTML(notif.title)}</div>
            <div class="notif-desc">${escapeHTML(notif.desc)}</div>
            <div class="notif-time">${notif.time}</div>
        `;
        container.appendChild(item);
    });
}

function clearNotifications() {
    localNotifications = [];
    saveLocalDatabase();
    renderNotifications();
    showSystemToast("All notifications cleared.");
}

function formatNotificationTime(date) {
    return date.toLocaleString('en-US', {
        month: 'short',
        day: 'numeric',
        hour: 'numeric',
        minute: '2-digit'
    });
}

function formatReminderOffset(minutes) {
    if (minutes === 0) return 'at task time';
    if (minutes < 60) return `${minutes} minute${minutes === 1 ? '' : 's'} before`;
    if (minutes < 1440) {
        const hours = Math.round(minutes / 60);
        return `${hours} hour${hours === 1 ? '' : 's'} before`;
    }
    const days = Math.round(minutes / 1440);
    return `${days} day${days === 1 ? '' : 's'} before`;
}

function notifyDevice(title, body) {
    if (!currentUser?.device_notifications_enabled || !('Notification' in window) || Notification.permission !== 'granted') {
        return;
    }
    try {
        new Notification(title, { body });
    } catch (err) {
        console.warn('Device notification failed', err);
    }
}

function addSystemNotification(title, desc, time = "Just now", type = "upcoming") {
    const fingerprint = `${title}|${desc}`;
    const recentlyExists = localNotifications.some(notif => notif.fingerprint === fingerprint);
    if (recentlyExists) return;
    localNotifications.unshift({
        id: Date.now(),
        title,
        desc,
        time,
        type,
        fingerprint
    });
    saveLocalDatabase();
    renderNotifications();
    notifyDevice(title, desc);
}

function startNotificationWatcher() {
    if (notificationWatcherStarted) return;
    notificationWatcherStarted = true;
    setInterval(checkTaskNotifications, 30000);
    checkTaskNotifications();
}

function checkTaskNotifications() {
    const source = isOnline ? calendarTasksCache : localTasks;
    if (!Array.isArray(source) || source.length === 0) return;
    const now = new Date();

    source.forEach(task => {
        if (!task || task.status === 'completed' || !task.date || !task.time) return;
        const due = new Date(`${task.date}T${normalizeTimeForInput(task.time)}:00`);
        if (Number.isNaN(due.getTime())) return;

        const reminderMinutes = Number(task.reminder_minutes_before ?? 10);
        const remindAt = new Date(due.getTime() - reminderMinutes * 60000);
        if (now >= remindAt && now <= due) {
            addSystemNotification(
                'Task reminder',
                `${task.title} is due ${formatReminderOffset(reminderMinutes)}.`,
                formatNotificationTime(now),
                'upcoming'
            );
        }
        if (now > due) {
            addSystemNotification(
                'Overdue task',
                `${task.title} is overdue.`,
                formatNotificationTime(now),
                'late'
            );
        }
    });
}

// --- NAVIGATION PANEL ROUTER ---
async function navigateTo(panelName) {
    dashboardPanel.classList.remove('active');
    calendarPanel.classList.remove('active');
    document.getElementById('settings-panel').classList.remove('active');
    
    document.getElementById('navHome').classList.remove('active');
    document.getElementById('navCalendar').classList.remove('active');

    closeAllHeaderPopups();

    if (panelName === 'dashboard') {
        dashboardPanel.classList.add('active');
        document.getElementById('navHome').classList.add('active');
        fetchDashboardData();
    } else if (panelName === 'calendar') {
        calendarPanel.classList.add('active');
        document.getElementById('navCalendar').classList.add('active');
        await fetchDashboardData();
        renderCalendarMatrix();
        inspectCalendarSelectedDayTasks();
    } else if (panelName === 'settings') {
        document.getElementById('settings-panel').classList.add('active');
        populateSettingsInputs();
        switchSettingsTab('profile');
    }
}

// --- INTERACTIVE WEB SPEECH & INTELLIGENT PARSER ---
function initVoiceRecognition() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

    if (!SpeechRecognition) {
        // Fallback to audio recording + server-side STT
        console.warn("Natively hosted Speech Recognition engines absent. Using MediaRecorder fallback.");

        let mediaRecorder = null;
        let audioChunks = [];

        micBtn.addEventListener('click', async () => {
            // Toggle recording
            if (micBtn.classList.contains('listening')) {
                // stop
                if (mediaRecorder && mediaRecorder.state !== 'inactive') {
                    mediaRecorder.stop();
                }
            } else {
                // start
                try {
                    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                    audioChunks = [];
                    mediaRecorder = new MediaRecorder(stream);
                    mediaRecorder.ondataavailable = (e) => audioChunks.push(e.data);
                    mediaRecorder.onstart = () => {
                        micBtn.classList.add('listening');
                        voiceToast.style.display = 'block';
                        voiceToast.textContent = "Speak now, I'm listening.";
                        playListeningChime();
                    };
                    mediaRecorder.onstop = async () => {
                        micBtn.classList.remove('listening');
                        voiceToast.style.display = 'none';
                        const blob = new Blob(audioChunks, { type: 'audio/webm' });
                        const form = new FormData();
                        form.append('audio', blob, 'voice.webm');
                        try {
                            const res = await apiFetchForm(ENDPOINTS.voiceAudio, form);
                            if (!res.ok) {
                                const body = await res.json().catch(() => ({}));
                                showSystemToast('Audio transcription failed: ' + formatApiError(body));
                                return;
                            }
                            const result = await res.json();
                            await handleVoiceCommandResult(result);
                        } catch (err) {
                            console.error('Audio upload failed', err);
                            showSystemToast('Audio upload failed. Ensure backend is running.');
                        }
                        // stop all tracks
                        stream.getTracks().forEach(t => t.stop());
                    };
                    mediaRecorder.start();
                } catch (err) {
                    console.error('MediaRecorder init failed', err);
                    showSystemToast('Microphone recording unavailable.');
                }
            }
        });
        return;
    }

    const recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.lang = (currentUser && currentUser.region && currentUser.region.includes('Japan')) ? 'ja-JP' : 'en-US';
    recognition.interimResults = true;

    let finalTranscript = '';
    let shouldKeepListening = false;
    let submitTimer = null;
    let isRecognitionRunning = false;
    let lastUpdateTime = Date.now();
    let isSubmittingVoice = false;
    let lastSubmittedVoice = '';
    let lastSubmittedAt = 0;

    function computeAdaptiveDelay() {
        // Base minimum to avoid premature submit, scale with word count
        const words = finalTranscript.split(/\s+/).filter(Boolean).length;
        const computed = Math.min(7000, 700 + words * 250);
        return computed;
    }

    function queueVoiceSubmit(delay = null) {
        clearTimeout(submitTimer);
        const useDelay = delay || computeAdaptiveDelay();
        submitTimer = setTimeout(() => {
            shouldKeepListening = false;
            submitCapturedSpeechOnce();
            if (isRecognitionRunning) {
                try {
                    recognition.stop();
                } catch (e) {
                    console.warn("Speech recognition stop error:", e);
                }
            }
        }, useDelay);
    }

    micBtn.addEventListener('click', () => {
        if (micBtn.classList.contains('listening')) {
            shouldKeepListening = false;
            submitCapturedSpeechOnce();
            if (isRecognitionRunning) {
                try {
                    recognition.stop();
                } catch (e) {
                    console.warn("Speech recognition stop error:", e);
                }
            }
        } else {
            finalTranscript = '';
            isSubmittingVoice = false;
            shouldKeepListening = true;
            if (!isRecognitionRunning) {
                try {
                    recognition.start();
                } catch (e) {
                    console.warn("Speech recognition start error:", e);
                    showSystemToast("Microphone unavailable. Try again shortly.");
                }
            }
        }
    });

    recognition.onstart = () => {
        isRecognitionRunning = true;
        micBtn.classList.add('listening');
        voiceToast.style.display = "block";
        voiceToast.textContent = "Speak now, I'm listening.";
        playListeningChime();
    };

    recognition.onend = () => {
        isRecognitionRunning = false;
        if (shouldKeepListening) {
            try {
                recognition.start();
            } catch (e) {
                console.warn("Speech restart skipped:", e);
            }
            return;
        }
        micBtn.classList.remove('listening');
        voiceToast.style.display = "none";
    };

    recognition.onerror = (event) => {
        console.error("Vocal engine capture error: ", event.error);
        shouldKeepListening = false;
        clearTimeout(submitTimer);
        micBtn.classList.remove('listening');
        voiceToast.style.display = "none";
        showSystemToast("Vocal error captured: " + event.error);
    };

    async function submitCapturedSpeechOnce() {
        const phrase = finalTranscript.trim();
        if (!phrase || isSubmittingVoice) return;

        const normalized = phrase.toLowerCase().replace(/\s+/g, ' ');
        const now = Date.now();
        if (normalized === lastSubmittedVoice && now - lastSubmittedAt < 8000) return;

        isSubmittingVoice = true;
        lastSubmittedVoice = normalized;
        lastSubmittedAt = now;
        clearTimeout(submitTimer);
        try {
            await processCapturedSpeech(phrase);
        } finally {
            finalTranscript = '';
            isSubmittingVoice = false;
        }
    }

    recognition.onresult = (event) => {
        let updated = false;
        for (let i = event.resultIndex; i < event.results.length; i++) {
            const transcriptPart = event.results[i][0].transcript.trim();
            if (event.results[i].isFinal && transcriptPart) {
                finalTranscript = `${finalTranscript} ${transcriptPart}`.trim();
                updated = true;
            } else if (!event.results[i].isFinal && transcriptPart) {
                // refresh last update time to delay submit while user keeps speaking
                lastUpdateTime = Date.now();
            }
        }
        if (updated) queueVoiceSubmit();
        else {
            // if interim results keep coming, extend the timeout slightly
            queueVoiceSubmit(1200);
        }
    };
}

// --- INTELLIGENT VOCAL NATURAL LANGUAGE PARSING ENGINE ---
async function processCapturedSpeech(phrase) {
    if (!phrase) return;
    console.log("Processing captured phrase:", phrase);
    showSystemToast(`Heard: "${phrase}"`);

    try {
        const response = await apiFetch(ENDPOINTS.voiceCommand, {
            method: 'POST',
            body: JSON.stringify({ transcript: phrase })
        });

        if (!response.ok) {
            // Attempt robust client-side parsing fallback before giving up
            const handledLocally = await tryLocalVoiceFallback(phrase);
            if (handledLocally) return;

            const errorBody = await response.json().catch(() => ({}));
            const errorText = formatApiError(errorBody);
            const authMessage = (response.status === 401 || response.status === 403)
                ? ' Please sign in before using voice commands.'
                : '';
            showSystemToast(`Voice task failed: ${errorText}.${authMessage}`);
            return;
        }

        const result = await response.json();
        await handleVoiceCommandResult(result);
    } catch (err) {
        console.error("Voice task backend request failed:", err);
        // Try local fallback parsing and insertion
        const handledLocally = await tryLocalVoiceFallback(phrase);
        if (handledLocally) return;
        showSystemToast("Voice task failed. Check if Django is running.");
    }
}

// CLIENT-SIDE REGEXP PARSING FALLBACK FOR VOICE COMMANDS
async function tryLocalVoiceFallback(phrase) {
    try {
        const payload = localParseVoice(phrase);
        if (!payload) return false;

        // Try to create via backend (best-effort)
        try {
            const resp = await apiFetch(ENDPOINTS.tasks, { method: 'POST', body: JSON.stringify(payload) });
            if (resp.ok) {
                const created = await resp.json();
                showSystemToast('Voice parsed locally and task created.');
                renderedTaskCache[created.id] = created;
                fetchDashboardData();
                return true;
            }
        } catch (err) {
            console.warn('Backend create failed, falling back to offline insertion:', err);
        }

        // Offline insertion fallback
        const newTask = { id: Date.now(), ...payload };
        localTasks.push(newTask);
        saveLocalDatabase();
        showSystemToast('Voice parsed locally and task saved offline.');
        fetchDashboardData();
        return true;
    } catch (err) {
        console.error('Local voice fallback failed:', err);
        return false;
    }
}

function localParseVoice(phrase) {
    if (!phrase) return null;
    const p = phrase.trim();
    // Normalize common words
    const lower = p.toLowerCase();

    // Only attempt to parse commands that start with add/create or similar
    if (!/^(add|create|new|dagdag|idagdag|magdagdag|gawa|gumawa|paalala)\b/i.test(p)) return null;

    // Extract priority
    let priority = 'medium';
    const prMatch = lower.match(/(?:priority|prayoridad)\s+(high|medium|low|mataas|katamtaman|mababa)/i);
    if (prMatch) {
        const priorityMap = { mataas: 'high', katamtaman: 'medium', mababa: 'low' };
        priority = priorityMap[prMatch[1]] || prMatch[1];
    }

    let category = 'Others';
    const categoryMatch = lower.match(/\b(?:category|kategorya|in|under|sa|para sa)\s+(school|paaralan|eskwela|skwela|klase|work|trabaho|opisina|personal|sarili|pansarili|others|other|iba)\b/i);
    if (categoryMatch) {
        const categoryMap = {
            paaralan: 'School',
            eskwela: 'School',
            skwela: 'School',
            klase: 'School',
            trabaho: 'Work',
            opisina: 'Work',
            sarili: 'Personal',
            pansarili: 'Personal',
            iba: 'Others',
            other: 'Others',
            others: 'Others'
        };
        category = categoryMap[categoryMatch[1]] || categoryMatch[1].charAt(0).toUpperCase() + categoryMatch[1].slice(1).toLowerCase();
    }

    // Extract date
    let date = null;
    if (/\b(tomorrow|bukas)\b/i.test(lower)) {
        const d = new Date(); d.setDate(d.getDate() + 1);
        date = d.toISOString().slice(0,10);
    } else if (/\b(today|ngayon|mamaya)\b/i.test(lower)) {
        const d = new Date(); date = d.toISOString().slice(0,10);
    } else {
        // ISO date detection
        const iso = p.match(/(\d{4}-\d{2}-\d{2})/);
        if (iso) date = iso[1];
        else {
            // Try natural month day like 'May 18' or 'June 3'
            const md = p.match(/on\s+([A-Za-z]+\s+\d{1,2})/i) || p.match(/([A-Za-z]+\s+\d{1,2})/i);
            if (md) {
                const parsed = Date.parse(md[1] + ' ' + new Date().getFullYear());
                if (!isNaN(parsed)) date = new Date(parsed).toISOString().slice(0,10);
            }
        }
    }

    // Extract time
    let time = null;
    const filipinoTimeMatch = lower.match(/\balas\s+(\d{1,2}|una|isa|uno|dalawa|dos|tatlo|tres|apat|kwatro|lima|singko|anim|sais|pito|siete|walo|otso|siyam|nueve|diez|sampu|onse|dose)(?:\s+(?:y\s+)?(?:media|trenta))?\s*(?:ng\s+)?(umaga|hapon|gabi)?\b/i);
    const timeMatch = p.match(/(\d{1,2}:\d{2}\s*(am|pm)?)/i) || p.match(/(\d{1,2}\s*(am|pm))/i);
    if (filipinoTimeMatch) {
        const numberMap = { una: 1, isa: 1, uno: 1, dalawa: 2, dos: 2, tatlo: 3, tres: 3, apat: 4, kwatro: 4, lima: 5, singko: 5, anim: 6, sais: 6, pito: 7, siete: 7, walo: 8, otso: 8, siyam: 9, nueve: 9, diez: 10, sampu: 10, onse: 11, dose: 12 };
        let hour = /^\d+$/.test(filipinoTimeMatch[1]) ? parseInt(filipinoTimeMatch[1], 10) : numberMap[filipinoTimeMatch[1]];
        const minute = /(media|trenta)/i.test(filipinoTimeMatch[0]) ? 30 : 0;
        const period = filipinoTimeMatch[2];
        if ((period === 'hapon' || period === 'gabi') && hour !== 12) hour += 12;
        if (period === 'umaga' && hour === 12) hour = 0;
        time = `${String(hour).padStart(2,'0')}:${String(minute).padStart(2,'0')}`;
    } else if (timeMatch) {
        let t = timeMatch[1].trim();
        // Normalize to HH:MM 24h
        let dt = Date.parse('01/01/1970 ' + t);
        if (!isNaN(dt)) {
            const d = new Date(dt);
            const hh = String(d.getHours()).padStart(2,'0');
            const mm = String(d.getMinutes()).padStart(2,'0');
            time = `${hh}:${mm}`;
        }
    }

    // Extract title: everything after 'add' until the first date/time/priority keyword
    const titleMatch = p.match(/^(?:add|create|new|dagdag|idagdag|magdagdag|gawa|gumawa|paalala)\s+(.+?)(?:\s+on\s+|\s+at\s+|\s+sa\s+|\s+alas\s+|\s+tomorrow\b|\s+today\b|\s+bukas\b|\s+ngayon\b|\s+mamaya\b|\s+priority\b|\s+prayoridad\b|$)/i);
    const title = titleMatch ? titleMatch[1].trim() : null;
    if (!title) return null;

    return {
        title: title.charAt(0).toUpperCase() + title.slice(1),
        date: date || getTodayDateString(),
        time: time || '',
        priority: priority,
        category_label: category,
        status: 'pending'
    };
}

async function handleVoiceCommandResult(result) {
    const message = result.message || 'Voice command processed.';
    showSystemToast(message);
    triggerVocalResponse(message);

    if (result.task) {
        renderedTaskCache[result.task.id] = result.task;
    }

    if (Array.isArray(result.tasks)) {
        calendarTasksCache = result.tasks;
        result.tasks.forEach(task => {
            renderedTaskCache[task.id] = task;
        });
        currentFilter = 'voice';
        if (document.getElementById('todayHeaderLabel')) document.getElementById('todayHeaderLabel').textContent = 'Voice Results';
        if (document.getElementById('upcomingHeaderLabel')) document.getElementById('upcomingHeaderLabel').textContent = '';
        const tasksLayout = document.querySelector('.tasks-layout');
        const columns = tasksLayout ? tasksLayout.querySelectorAll(':scope > div') : [];
        if (tasksLayout) tasksLayout.classList.add('filtered-mode');
        if (columns[1]) columns[1].style.display = 'none';
        renderTaskList(result.tasks, 'today-tasks-list', false, true);
        if (document.getElementById('upcoming-tasks-list')) document.getElementById('upcoming-tasks-list').innerHTML = '';
        navigateTo('dashboard');
        return;
    }

    if (result.action === 'navigate') {
        const target = result.target === 'profile' ? 'settings' : result.target;
        navigateTo(target || 'dashboard');
        return;
    }

    if (result.action === 'logout') {
        currentUser = null;
        localStorage.removeItem('vast_user');
        appContentWrapper.style.display = 'none';
        authPageWrapper.style.display = 'flex';
        return;
    }

    if ((result.action === 'task_summary' || result.action === 'how_to') && result.result) {
        renderAIResult(result.result);
    }

    if (currentFilter === 'voice') {
        currentFilter = 'all';
    }
    await fetchDashboardData();
    navigateTo('dashboard');
}

async function initAIActions() {
    const summaryBtn = document.getElementById('aiSummaryBtn');
    const howToBtn = document.getElementById('howToBtn');
    const collapseBtn = document.getElementById('aiCollapseBtn');
    if (summaryBtn) {
        summaryBtn.addEventListener('click', fetchAISummary);
    }
    if (howToBtn) {
        howToBtn.addEventListener('click', renderHowToGuide);
    }
    if (collapseBtn) {
        collapseBtn.addEventListener('click', () => {
            const section = collapseBtn.closest('.ai-section');
            const panel = document.getElementById('aiResultPanel');
            if (!section || !panel || panel.dataset.hasResult !== 'true') return;

            section.classList.remove('collapsed');
            panel.textContent = 'Run a summary or open the guide for voice-assisted scheduling tips.';
            panel.dataset.hasResult = 'false';
            panel.style.display = 'block';
            collapseBtn.textContent = 'Collapse';
        });
    }
}

async function fetchAISummary() {
    try {
        const response = await apiFetch(ENDPOINTS.aiSummary, { method: 'POST' });
        if (!response.ok) {
            showSystemToast('AI summary failed. Please sign in and try again.');
            return;
        }
        renderAIResult(await response.json());
    } catch (err) {
        console.error('AI summary request failed:', err);
        showSystemToast('AI summary failed. Check the backend server.');
    }
}

async function executeTool(slug) {
    try {
        const response = await apiFetch(`${ENDPOINTS.tools}${slug}/execute/`, {
            method: 'POST',
            body: JSON.stringify({})
        });
        if (!response.ok) {
            showSystemToast('AI tool execution failed.');
            return;
        }
        const payload = await response.json();
        renderAIResult(payload.result || payload);
    } catch (err) {
        console.error('AI tool execution failed:', err);
        showSystemToast('AI tool execution failed. Check the backend server.');
    }
}

function renderHowToGuide() {
    renderAIResult({
        summary: 'Use short, complete voice commands with an action, task name, date, time, priority, and category.',
        recommendations: [
            'Say: "Add math quiz tomorrow at 3 PM priority high category School."',
            'Update tasks with: "Move math quiz to Friday at 10 AM" or "Change math quiz priority high."',
            'Delete or finish tasks with: "Delete math quiz" or "Complete math quiz."',
            'Use categories: School, Work, Personal, or Others.',
            'Filipino cues are supported: "dagdag", "gumawa", "bukas", "ngayon", "tapusin", "burahin", and "hanapin".'
        ]
    });
}

function renderAIResult(result) {
    const panel = document.getElementById('aiResultPanel');
    if (!panel) {
        showSystemToast(result.summary || result.insight || 'AI result is ready.');
        return;
    }

    const summary = result.summary || result.insight || 'AI analysis complete.';
    const recommendations = result.recommendations || [];
    const recommendationHTML = recommendations.length
        ? `<ul>${recommendations.map(item => `<li>${escapeHTML(String(item))}</li>`).join('')}</ul>`
        : '';

    let metricHTML = '';
    if (typeof result.pending_count !== 'undefined') {
        metricHTML = `
            <div class="ai-metrics">
                <span>${result.pending_count} pending</span>
                <span>${result.completed_count} completed</span>
                <span>${result.overdue_count} overdue</span>
            </div>
        `;
    }

    panel.innerHTML = `
        <strong>AI Insight</strong>
        <p>${escapeHTML(summary)}</p>
        ${metricHTML}
        ${recommendationHTML}
    `;
    panel.dataset.hasResult = 'true';
    panel.style.display = 'block';
    panel.closest('.ai-section')?.classList.remove('collapsed');
    triggerVocalResponse(summary);
}

// Voice simulator fallback for non-Chrome platforms
function simulateVocalPrompt() {
    const mockCommand = prompt(
        "V.A.S.T. Vocal Command Interface Sandbox Simulator:\n\n" +
        "Try typing vocal statements like:\n" +
        "• 'Add math quiz tomorrow at 03:00 PM priority high'\n" +
        "• 'Add buy milk today at 08:30 AM'\n" +
        "• 'Add presentation on May 18 at 01:00 PM'"
    );
    if (mockCommand) {
        processCapturedSpeech(mockCommand);
    }
}

// Custom SpeechSynthesis utility
function triggerVocalResponse(phrase) {
    if ('speechSynthesis' in window) {
        window.speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance(phrase);
        utterance.pitch = 1.0;
        utterance.rate = 1.0;
        window.speechSynthesis.speak(utterance);
    }
}

function playListeningChime() {
    try {
        const AudioContext = window.AudioContext || window.webkitAudioContext;
        if (!AudioContext) return;
        const context = new AudioContext();
        const oscillator = context.createOscillator();
        const gain = context.createGain();
        oscillator.type = 'sine';
        oscillator.frequency.setValueAtTime(880, context.currentTime);
        gain.gain.setValueAtTime(0.001, context.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.08, context.currentTime + 0.02);
        gain.gain.exponentialRampToValueAtTime(0.001, context.currentTime + 0.18);
        oscillator.connect(gain);
        gain.connect(context.destination);
        oscillator.start();
        oscillator.stop(context.currentTime + 0.2);
    } catch (err) {
        console.warn('Listening chime unavailable', err);
    }
}

// --- INTERACTION UTILITY HELPERS ---
function toggleModal(show) {
    taskModal.classList.toggle('active', show);
}

openModalBtn.addEventListener('click', () => toggleModal(true));
closeModalBtn.addEventListener('click', () => toggleModal(false));
taskModal.addEventListener('click', (e) => {
    if (e.target === taskModal) toggleModal(false);
});

function showSystemToast(message) {
    systemAlert.textContent = message;
    systemAlert.style.display = 'flex';
    setTimeout(() => {
        systemAlert.style.display = 'none';
    }, 3500);
}

// Time format utility
function formatTime(timeString) {
    if (!timeString) return '';
    const [hours, minutes] = timeString.split(':');
    let hourInt = parseInt(hours, 10);
    const ampm = hourInt >= 12 ? 'PM' : 'AM';
    hourInt = hourInt % 12 || 12;
    return `${String(hourInt).padStart(2, '0')}:${minutes} ${ampm}`;
}

function formatShortDate(dateStr) {
    const dateObj = new Date(dateStr);
    const options = { month: 'short', day: 'numeric' };
    return dateObj.toLocaleDateString('en-US', options);
}

function getTodayDateString() {
    const today = new Date();
    const year = today.getFullYear();
    const month = String(today.getMonth() + 1).padStart(2, '0');
    const day = String(today.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}

function normalizeTimeForInput(timeString) {
    if (!timeString) return "09:00";
    return timeString.slice(0, 5);
}

// Prevent injection vulnerabilities
function escapeHTML(str) {
    return str.replace(/[&<>'"]/g, tag => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
    }[tag] || tag));
}

function formatApiError(errorBody) {
    if (!errorBody || typeof errorBody !== 'object') {
        return 'Request failed. Check the browser console.';
    }
    if (errorBody.detail) {
        return errorBody.detail;
    }
    if (errorBody.error) {
        return errorBody.error;
    }

    return Object.entries(errorBody)
        .map(([field, messages]) => `${field}: ${Array.isArray(messages) ? messages.join(', ') : messages}`)
        .join('\n') || 'Request failed. Check the browser console.';
}