(() => {
  const STORAGE_KEY = 'theme';

  const getStoredTheme = () => localStorage.getItem(STORAGE_KEY);

  const getPreferredTheme = () => {
    const stored = getStoredTheme();
    if (stored) return stored;
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  };

  const setTheme = (theme) => {
    document.documentElement.setAttribute('data-bs-theme', theme);
    localStorage.setItem(STORAGE_KEY, theme);

    const sw = document.getElementById('theme-toggle');
    if (sw) sw.checked = (theme === 'dark');
  };

  // Apply initial theme as early as possible
  setTheme(getPreferredTheme());

  // If user hasn’t set a preference, follow OS changes live
  const media = window.matchMedia('(prefers-color-scheme: dark)');
  media.addEventListener('change', () => {
    if (!getStoredTheme()) setTheme(getPreferredTheme());
  });

  // Attach toggle handler
  window.addEventListener('DOMContentLoaded', () => {
    const sw = document.getElementById('theme-toggle');
    if (!sw) return;
    sw.checked = (getPreferredTheme() === 'dark');
    sw.addEventListener('change', (e) => setTheme(e.target.checked ? 'dark' : 'light'));
  });
})();
