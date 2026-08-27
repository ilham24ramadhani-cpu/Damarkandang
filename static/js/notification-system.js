/**
 * Notification System
 * Sistem notifikasi untuk menampilkan aktivitas CRUD di semua modul
 */

// Inisialisasi sistem notifikasi
(function() {
  'use strict';

  // Storage key untuk notifikasi
  const NOTIFICATION_STORAGE_KEY = 'damarkandang_notifications';
  const MAX_NOTIFICATIONS = 50; // Maksimal jumlah notifikasi yang disimpan

  /**
   * Mendapatkan semua notifikasi dari storage
   */
  function getNotifications() {
    try {
      const stored = localStorage.getItem(NOTIFICATION_STORAGE_KEY);
      return stored ? JSON.parse(stored) : [];
    } catch (error) {
      console.error('Error reading notifications:', error);
      return [];
    }
  }

  /**
   * Menyimpan notifikasi ke storage
   */
  function saveNotifications(notifications) {
    try {
      // Batasi jumlah notifikasi
      const limited = notifications.slice(0, MAX_NOTIFICATIONS);
      localStorage.setItem(NOTIFICATION_STORAGE_KEY, JSON.stringify(limited));
    } catch (error) {
      console.error('Error saving notifications:', error);
    }
  }

  /**
   * Menambahkan notifikasi baru
   */
  function addNotification(type, module, status = 'success', customMessage = null) {
    const messages = {
      create: {
        Pengguna: 'Pengguna berhasil ditambahkan',
        Bahan: 'Bahan berhasil ditambahkan',
        Produksi: 'Produksi berhasil ditambahkan',
        Pemesanan: 'Pemesanan berhasil ditambahkan',
        Sanitasi: 'Data sanitasi berhasil ditambahkan',
        Pemasok: 'Pemasok berhasil ditambahkan',
        Keuangan: 'Data keuangan berhasil ditambahkan',
        Produk: 'Produk berhasil ditambahkan',
        Proses: 'Proses pengolahan berhasil ditambahkan',
        JenisKopi: 'Jenis kopi berhasil ditambahkan',
        Varietas: 'Varietas berhasil ditambahkan',
        Roasting: 'Level roasting berhasil ditambahkan',
        Kemasan: 'Kemasan berhasil ditambahkan'
      },
      update: {
        Pengguna: 'Pengguna berhasil diperbarui',
        Bahan: 'Bahan berhasil diperbarui',
        Produksi: 'Produksi berhasil diperbarui',
        Pemesanan: 'Pemesanan berhasil diperbarui',
        Sanitasi: 'Data sanitasi berhasil diperbarui',
        Pemasok: 'Pemasok berhasil diperbarui',
        Keuangan: 'Data keuangan berhasil diperbarui',
        Produk: 'Produk berhasil diperbarui',
        Proses: 'Proses pengolahan berhasil diperbarui',
        JenisKopi: 'Jenis kopi berhasil diperbarui',
        Varietas: 'Varietas berhasil diperbarui',
        Roasting: 'Level roasting berhasil diperbarui',
        Kemasan: 'Kemasan berhasil diperbarui'
      },
      delete: {
        Pengguna: 'Pengguna berhasil dihapus',
        Bahan: 'Bahan berhasil dihapus',
        Produksi: 'Produksi berhasil dihapus',
        Pemesanan: 'Pemesanan berhasil dihapus',
        Sanitasi: 'Data sanitasi berhasil dihapus',
        Pemasok: 'Pemasok berhasil dihapus',
        Keuangan: 'Data keuangan berhasil dihapus',
        Produk: 'Produk berhasil dihapus',
        Proses: 'Proses pengolahan berhasil dihapus',
        JenisKopi: 'Jenis kopi berhasil dihapus',
        Varietas: 'Varietas berhasil dihapus',
        Roasting: 'Level roasting berhasil dihapus',
        Kemasan: 'Kemasan berhasil dihapus'
      }
    };

    const message = customMessage || (messages[type] && messages[type][module]) || 'Operasi berhasil';
    const icon = status === 'success' ? 'bi-check-circle-fill text-success' : 'bi-exclamation-triangle-fill text-danger';
    
    const notification = {
      id: Date.now() + Math.random(),
      type: type,
      module: module,
      message: message,
      status: status,
      icon: icon,
      timestamp: new Date().toISOString(),
      read: false
    };

    const notifications = getNotifications();
    notifications.unshift(notification); // Tambahkan di awal
    saveNotifications(notifications);

    // Update UI
    updateNotificationBadge();
    updateNotificationDropdown();

    return notification;
  }

  /**
   * Menandai notifikasi sebagai sudah dibaca
   */
  function markAsRead(notificationId) {
    const notifications = getNotifications();
    const notification = notifications.find(n => n.id === notificationId);
    if (notification) {
      notification.read = true;
      saveNotifications(notifications);
      updateNotificationBadge();
      updateNotificationDropdown();
    }
  }

  /**
   * Menandai semua notifikasi sebagai sudah dibaca
   */
  function markAllAsRead() {
    const notifications = getNotifications();
    notifications.forEach(n => n.read = true);
    saveNotifications(notifications);
    updateNotificationBadge();
    updateNotificationDropdown();
  }

  /**
   * Menghapus notifikasi
   */
  function removeNotification(notificationId) {
    const notifications = getNotifications();
    const filtered = notifications.filter(n => n.id !== notificationId);
    saveNotifications(filtered);
    updateNotificationBadge();
    updateNotificationDropdown();
  }

  /**
   * Menghapus semua notifikasi
   */
  function clearAllNotifications() {
    saveNotifications([]);
    updateNotificationBadge();
    updateNotificationDropdown();
  }

  /**
   * Format waktu relatif (misalnya "2 menit yang lalu")
   */
  function formatRelativeTime(timestamp) {
    const now = new Date();
    const time = new Date(timestamp);
    const diffMs = now - time;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'Baru saja';
    if (diffMins < 60) return `${diffMins} menit yang lalu`;
    if (diffHours < 24) return `${diffHours} jam yang lalu`;
    if (diffDays < 7) return `${diffDays} hari yang lalu`;
    
    return time.toLocaleDateString('id-ID', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  }

  /**
   * Update badge notifikasi
   */
  function updateNotificationBadge() {
    const notifications = getNotifications();
    const unreadCount = notifications.filter(n => !n.read).length;
    const badgeElements = document.querySelectorAll('#notificationBadge');
    
    badgeElements.forEach(badge => {
      if (unreadCount > 0) {
        badge.textContent = unreadCount > 99 ? '99+' : unreadCount;
        badge.style.display = 'inline-block';
      } else {
        badge.textContent = '';
        badge.style.display = 'none';
      }
    });
  }

  /**
   * Update dropdown notifikasi
   */
  function updateNotificationDropdown() {
    const notifications = getNotifications();
    const dropdownBody = document.getElementById('notificationDropdownBody');
    const emptyState = document.getElementById('notificationEmptyState');
    
    if (!dropdownBody) return;

    if (notifications.length === 0) {
      dropdownBody.innerHTML = '';
      if (emptyState) {
        emptyState.style.display = 'block';
      }
      return;
    }

    if (emptyState) {
      emptyState.style.display = 'none';
    }

    // Tampilkan maksimal 10 notifikasi terbaru
    const recentNotifications = notifications.slice(0, 10);
    
    dropdownBody.innerHTML = recentNotifications.map(notif => {
      const timeAgo = formatRelativeTime(notif.timestamp);
      const readClass = notif.read ? '' : 'bg-light';
      
      return `
        <li class="notification-item ${readClass}" data-id="${notif.id}">
          <div class="d-flex align-items-start p-2">
            <div class="flex-shrink-0 me-2 mt-1">
              <i class="${notif.icon}"></i>
            </div>
            <div class="flex-grow-1">
              <div class="small fw-semibold">${notif.message}</div>
              <div class="text-muted" style="font-size: 0.75rem;">${timeAgo}</div>
            </div>
            <button 
              class="btn-close btn-close-sm ms-2 flex-shrink-0" 
              onclick="event.stopPropagation(); window.NotificationSystem.removeNotification(${notif.id}); return false;"
              aria-label="Hapus"
            ></button>
          </div>
        </li>
      `;
    }).join('');

    // Tambahkan event listener untuk mark as read
    dropdownBody.querySelectorAll('.notification-item').forEach(item => {
      item.addEventListener('click', function(e) {
        if (e.target.classList.contains('btn-close')) return;
        const id = parseFloat(this.dataset.id);
        window.NotificationSystem.markAsRead(id);
      });
    });
  }

  /**
   * Inisialisasi sistem notifikasi
   */
  function init() {
    // Tunggu DOM siap
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', function() {
        updateNotificationBadge();
        updateNotificationDropdown();
      });
    } else {
      updateNotificationBadge();
      updateNotificationDropdown();
    }

    // Update setiap 30 detik untuk refresh waktu relatif
    setInterval(() => {
      updateNotificationDropdown();
    }, 30000);
  }

  // Export API
  window.NotificationSystem = {
    add: addNotification,
    markAsRead: markAsRead,
    markAllAsRead: markAllAsRead,
    removeNotification: removeNotification,
    clearAll: clearAllNotifications,
    updateBadge: updateNotificationBadge,
    updateDropdown: updateNotificationDropdown,
    getNotifications: getNotifications,
    init: init
  };

  // Override showNotification dari api-service.js untuk juga menyimpan ke sistem notifikasi
  // Tunggu sampai api-service.js selesai dimuat
  function integrateWithCRUDNotifications() {
    if (window.showNotification) {
      const originalShowNotification = window.showNotification;
      window.showNotification = function(type, module, status = 'success', customMessage = null) {
        // Panggil fungsi asli untuk toast notification
        originalShowNotification(type, module, status, customMessage);
        
        // Tambahkan ke sistem notifikasi (hanya untuk success)
        if (status === 'success') {
          addNotification(type, module, status, customMessage);
        }
      };
      console.log('✅ Notification system integrated with CRUD notifications');
    } else {
      // Jika api-service.js belum dimuat, coba lagi setelah delay
      setTimeout(integrateWithCRUDNotifications, 200);
    }
  }
  
  // Mulai integrasi setelah DOM ready dan api-service.js dimuat
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function() {
      setTimeout(integrateWithCRUDNotifications, 300);
    });
  } else {
    setTimeout(integrateWithCRUDNotifications, 300);
  }

  // Inisialisasi
  init();
})();
