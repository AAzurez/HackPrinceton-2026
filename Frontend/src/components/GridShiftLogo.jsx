export default function GridShiftLogo({ className = "h-11 w-11" }) {
  return (
    <svg
      className={className}
      viewBox="0 0 64 64"
      role="img"
      aria-label="GridShift logo"
      xmlns="http://www.w3.org/2000/svg"
    >
      <defs>
        <linearGradient id="gridshift_logo_bg" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#A48CF6" />
          <stop offset="100%" stopColor="#7B64DB" />
        </linearGradient>
        <linearGradient id="gridshift_logo_wave" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="#FFF8EE" />
          <stop offset="100%" stopColor="#F2CF80" />
        </linearGradient>
      </defs>
      <rect x="2" y="2" width="60" height="60" rx="18" fill="url(#gridshift_logo_bg)" />
      <path
        d="M12 38C19 24 30 24 36 34C41 42 49 44 54 30"
        fill="none"
        stroke="url(#gridshift_logo_wave)"
        strokeWidth="6"
        strokeLinecap="round"
      />
      <circle cx="16" cy="18" r="3.2" fill="#FFF6E6" fillOpacity="0.85" />
      <circle cx="48" cy="47" r="2.6" fill="#FCE5B8" fillOpacity="0.9" />
    </svg>
  );
}
