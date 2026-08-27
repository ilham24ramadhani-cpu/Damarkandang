// Profile Management (Admin)
let currentUser = null;

// Load user data from sessionStorage and API or localStorage
async function loadUserProfile() {
  // Get data from sessionStorage
  const sessionUsername = sessionStorage.getItem("username") || "Admin";
  const sessionRole = sessionStorage.getItem("userRole") || "Admin";
  const sessionUserId = sessionStorage.getItem("userId");
  const sessionEmail =
    sessionStorage.getItem("userEmail") || `${sessionUsername}@damarkandang.com`;

  // Try to find user in API or localStorage users by username first (most important)
  let users = [];
  try {
    if (window.API && window.API.Users) {
      users = await window.API.Users.getAll();
    } else {
      users = JSON.parse(localStorage.getItem("users") || "[]");
    }
  } catch (error) {
    console.error("Error loading users:", error);
    users = JSON.parse(localStorage.getItem("users") || "[]");
  }

  let userData = users.find((u) => u.username === sessionUsername);

  // If not found by username, try by userId
  if (!userData && sessionUserId) {
    userData = users.find((u) => u.id === parseInt(sessionUserId));
  }

  // If user found in localStorage, use it; otherwise create new user or use sessionStorage data
  if (userData) {
    // If found by userId and username doesn't match, update username to sessionUsername
    const finalUsername =
      userData.username === sessionUsername
        ? userData.username
        : sessionUsername;
    currentUser = {
      id: userData.id,
      namaLengkap: userData.namaLengkap || sessionUsername,
      username: finalUsername,
      email: userData.email || sessionEmail,
      noTelepon: userData.noTelepon || "",
      tanggalLahir: userData.tanggalLahir || "",
      jenisKelamin: userData.jenisKelamin || "",
      alamat: userData.alamat || "",
      role: userData.role || sessionRole,
      status: userData.status || "Aktif",
    };
  } else {
    // Check if there's saved currentUser data
    const savedCurrentUser = JSON.parse(localStorage.getItem("currentUser"));
    if (savedCurrentUser && savedCurrentUser.username === sessionUsername) {
      currentUser = savedCurrentUser;
    } else if (
      savedCurrentUser &&
      savedCurrentUser.username !== sessionUsername
    ) {
      // Username changed, update with new session data
      currentUser = {
        ...savedCurrentUser,
        username: sessionUsername,
        namaLengkap: savedCurrentUser.namaLengkap || sessionUsername,
        email: sessionEmail,
        role: sessionRole,
      };
      localStorage.setItem("currentUser", JSON.stringify(currentUser));
    } else {
      // Create new user data from sessionStorage
      // Generate new ID if needed
      const maxId =
        users.length > 0 ? Math.max(...users.map((u) => u.id || 0)) : 0;
      currentUser = {
        id: sessionUserId ? parseInt(sessionUserId) : maxId + 1,
        namaLengkap: sessionUsername, // Set namaLengkap to username initially
        username: sessionUsername,
        email: sessionEmail,
        noTelepon: "",
        tanggalLahir: "",
        jenisKelamin: "",
        alamat: "",
        role: sessionRole,
        status: "Aktif",
      };

      // Save to localStorage for future use
      localStorage.setItem("currentUser", JSON.stringify(currentUser));
    }
  }

  // Populate form
  document.getElementById("namaLengkap").value = currentUser.namaLengkap || "";
  document.getElementById("username").value = currentUser.username || "";
  document.getElementById("email").value = currentUser.email || "";
  document.getElementById("noTelepon").value = currentUser.noTelepon || "";
  document.getElementById("tanggalLahir").value =
    currentUser.tanggalLahir || "";
  document.getElementById("jenisKelamin").value =
    currentUser.jenisKelamin || "";
  document.getElementById("alamat").value = currentUser.alamat || "";

  // Update profile display
  const profileName = document.getElementById("profileName");
  const profileRole = document.getElementById("profileRole");
  const profileStatus = document.getElementById("profileStatus");
  const profileIcon = document.getElementById("profileIcon");

  if (profileName) {
    // Prioritize namaLengkap if it's different from username, otherwise show username
    const displayName =
      currentUser.namaLengkap &&
      currentUser.namaLengkap !== currentUser.username
        ? currentUser.namaLengkap
        : currentUser.username || sessionUsername || "Admin Sistem";
    profileName.textContent = displayName;
  }
  if (profileRole) {
    profileRole.textContent = currentUser.role || "Admin";
    // Set badge color based on role
    if (currentUser.role === "Admin") {
      profileRole.className = "badge bg-primary";
    } else if (currentUser.role === "Karyawan") {
      profileRole.className = "badge bg-info";
    } else if (currentUser.role === "Owner") {
      profileRole.className = "badge bg-warning text-dark";
    }
  }
  if (profileStatus) {
    profileStatus.textContent = currentUser.status || "Aktif";
    // Update badge color based on status
    profileStatus.className =
      currentUser.status === "Aktif"
        ? "badge bg-success"
        : "badge bg-secondary";
  }
  if (profileIcon) {
    // Admin icon
    profileIcon.className = "bi bi-person-circle profile-icon";
  }

  // Update statistik based on role
  updateStatistics();
}

// Update statistics based on role
function updateStatistics() {
  // Calculate statistics for admin
  const bahan = JSON.parse(localStorage.getItem("bahan")) || [];
  const produksi = JSON.parse(localStorage.getItem("produksi")) || [];
  const sanitasi = JSON.parse(localStorage.getItem("sanitasi")) || [];

  // You can add more statistics here if needed
  // For now, just show basic info
}

// Save profile
async function saveProfile(event) {
  event.preventDefault();

  // Get form values
  currentUser.namaLengkap = document.getElementById("namaLengkap").value;
  currentUser.username = document.getElementById("username").value;
  currentUser.email = document.getElementById("email").value;
  currentUser.noTelepon = document.getElementById("noTelepon").value;
  currentUser.tanggalLahir = document.getElementById("tanggalLahir").value;
  currentUser.jenisKelamin = document.getElementById("jenisKelamin").value;
  currentUser.alamat = document.getElementById("alamat").value;

  try {
    const userData = {
      namaLengkap: currentUser.namaLengkap,
      username: currentUser.username,
      email: currentUser.email,
      noTelepon: currentUser.noTelepon,
      tanggalLahir: currentUser.tanggalLahir,
      jenisKelamin: currentUser.jenisKelamin,
      alamat: currentUser.alamat,
      role: currentUser.role,
    };

    // Update in API or localStorage users if exists (search by username first, then by id)
    if (window.API && window.API.Users && currentUser.id) {
      // Update via API
      await window.API.Users.update(currentUser.id, userData);
    } else {
      // Fallback to localStorage
      const users = JSON.parse(localStorage.getItem("users") || "[]");
      let userIndex = users.findIndex(
        (u) => u.username === currentUser.username
      );

      // If not found by username, try by id
      if (userIndex === -1) {
        userIndex = users.findIndex((u) => u.id === currentUser.id);
      }

      if (userIndex !== -1) {
        // Update existing user
        users[userIndex] = { ...users[userIndex], ...userData };
      } else {
        // Add new user to users array
        users.push({
          id: currentUser.id,
          ...userData,
          password: "",
          status: currentUser.status,
        });
      }

      localStorage.setItem("users", JSON.stringify(users));
    }

    // Trigger event untuk update dashboard
    window.dispatchEvent(
      new CustomEvent("dataUpdated", { detail: { type: "users" } })
    );

    // Save to localStorage currentUser
    localStorage.setItem("currentUser", JSON.stringify(currentUser));

    // Update sessionStorage
    sessionStorage.setItem("username", currentUser.username);
    sessionStorage.setItem("userEmail", currentUser.email);

    // Update display
    document.getElementById("profileName").textContent =
      currentUser.namaLengkap;
    document.getElementById("profileRole").textContent = currentUser.role;

    // Show success message
    alert("Profile berhasil disimpan!");
  } catch (error) {
    console.error("Error saving profile:", error);
    alert("Error menyimpan profile: " + (error.message || "Unknown error"));
  }
}

// Initialize
document.addEventListener("DOMContentLoaded", () => {
  setTimeout(async () => {
    try {
      await loadUserProfile();
    } catch (error) {
      console.error("Error loading user profile:", error);
    }
  }, 100);

  const profileForm = document.getElementById("profileForm");
  if (profileForm) {
    profileForm.addEventListener("submit", saveProfile);
  }
});
