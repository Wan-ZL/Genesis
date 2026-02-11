/**
 * PWA support for Genesis
 * - Service worker registration
 * - Install prompt handling
 * - Push notification support
 */

// Service Worker Registration
if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
        navigator.serviceWorker.register('/static/sw.js')
            .then(registration => {
                console.log('[PWA] Service worker registered:', registration.scope);

                // Check for updates periodically
                setInterval(() => {
                    registration.update();
                }, 60000); // Check every minute
            })
            .catch(error => {
                console.error('[PWA] Service worker registration failed:', error);
            });
    });
}

// Install prompt handling
let deferredPrompt;
const installBanner = document.getElementById('pwa-install-banner');
const installBtn = document.getElementById('pwa-install-btn');
const dismissBtn = document.getElementById('pwa-dismiss-btn');

window.addEventListener('beforeinstallprompt', (e) => {
    console.log('[PWA] Install prompt available');

    // Prevent the default mini-infobar
    e.preventDefault();

    // Store the event for later use
    deferredPrompt = e;

    // Check if user has dismissed the banner before
    const dismissed = localStorage.getItem('pwa-install-dismissed');
    if (!dismissed && installBanner) {
        installBanner.classList.remove('hidden');
    }
});

// Install button click handler
if (installBtn) {
    installBtn.addEventListener('click', async () => {
        if (!deferredPrompt) {
            console.log('[PWA] No install prompt available');
            return;
        }

        // Show the install prompt
        deferredPrompt.prompt();

        // Wait for the user's response
        const { outcome } = await deferredPrompt.userChoice;
        console.log('[PWA] Install prompt outcome:', outcome);

        // Hide the banner
        if (installBanner) {
            installBanner.classList.add('hidden');
        }

        // Clear the deferred prompt
        deferredPrompt = null;
    });
}

// Dismiss button click handler
if (dismissBtn) {
    dismissBtn.addEventListener('click', () => {
        if (installBanner) {
            installBanner.classList.add('hidden');
        }

        // Remember that user dismissed the banner
        localStorage.setItem('pwa-install-dismissed', 'true');
    });
}

// Detect when app is installed
window.addEventListener('appinstalled', () => {
    console.log('[PWA] App installed');

    // Hide the banner
    if (installBanner) {
        installBanner.classList.add('hidden');
    }

    // Clear dismissed flag
    localStorage.removeItem('pwa-install-dismissed');
});

// Push Notification Support
async function requestNotificationPermission() {
    if (!('Notification' in window)) {
        console.log('[PWA] Push notifications not supported');
        return false;
    }

    if (Notification.permission === 'granted') {
        return true;
    }

    if (Notification.permission !== 'denied') {
        const permission = await Notification.requestPermission();
        return permission === 'granted';
    }

    return false;
}

async function subscribeToPushNotifications() {
    try {
        const registration = await navigator.serviceWorker.ready;

        // Check if already subscribed
        let subscription = await registration.pushManager.getSubscription();

        if (!subscription) {
            // Request permission
            const hasPermission = await requestNotificationPermission();
            if (!hasPermission) {
                console.log('[PWA] Notification permission denied');
                return null;
            }

            // Get VAPID public key from server
            const response = await fetch('/api/push/vapid-key');
            const data = await response.json();
            const publicKey = data.public_key;

            // Subscribe to push notifications
            subscription = await registration.pushManager.subscribe({
                userVisibleOnly: true,
                applicationServerKey: urlBase64ToUint8Array(publicKey)
            });

            console.log('[PWA] Push subscription created:', subscription);

            // Send subscription to server
            await fetch('/api/push/subscribe', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(subscription)
            });

            console.log('[PWA] Subscription sent to server');
        }

        return subscription;
    } catch (error) {
        console.error('[PWA] Push subscription error:', error);
        return null;
    }
}

// Helper function to convert VAPID key
function urlBase64ToUint8Array(base64String) {
    const padding = '='.repeat((4 - base64String.length % 4) % 4);
    const base64 = (base64String + padding)
        .replace(/\-/g, '+')
        .replace(/_/g, '/');

    const rawData = window.atob(base64);
    const outputArray = new Uint8Array(rawData.length);

    for (let i = 0; i < rawData.length; ++i) {
        outputArray[i] = rawData.charCodeAt(i);
    }

    return outputArray;
}

// Auto-subscribe to push notifications if permission granted
if ('serviceWorker' in navigator && 'PushManager' in window) {
    navigator.serviceWorker.ready.then(async () => {
        if (Notification.permission === 'granted') {
            await subscribeToPushNotifications();
        }
    });
}

// Expose functions globally for settings page to use
window.PWA = {
    requestNotificationPermission,
    subscribeToPushNotifications,
    getNotificationPermission: () => {
        return 'Notification' in window ? Notification.permission : 'unsupported';
    },
    isInstalled: () => {
        // Check if running as standalone PWA
        return window.matchMedia('(display-mode: standalone)').matches ||
               window.navigator.standalone === true;
    }
};

// Log PWA status on load
console.log('[PWA] Status:', {
    serviceWorker: 'serviceWorker' in navigator,
    pushManager: 'PushManager' in window,
    notification: 'Notification' in window,
    notificationPermission: 'Notification' in window ? Notification.permission : 'unsupported',
    isInstalled: window.PWA.isInstalled()
});
