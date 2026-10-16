/** CareerCompass compass mark + wordmark. */
export default function BrandLogo() {
  return (
    <span className="flex items-center gap-2.5">
      <svg
        width="34"
        height="34"
        viewBox="0 0 36 36"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className="rounded-lg shadow-[0_4px_10px_-2px_rgba(67,56,202,0.35)]"
        aria-hidden="true"
      >
        <rect width="36" height="36" rx="8" fill="url(#ccBrandGrad)" />
        <circle cx="18" cy="18" r="11" stroke="#FFFFFF" strokeWidth="1.6" strokeOpacity="0.35" strokeDasharray="2 2.5" />
        <circle cx="18" cy="18" r="13.8" stroke="#FFFFFF" strokeWidth="1" strokeOpacity="0.2" />
        <path d="M18 6.5L21.2 16.5L18 15.2L14.8 16.5L18 6.5Z" fill="#FFFFFF" />
        <path d="M18 29.5L21.2 19.5L18 20.8L14.8 19.5L18 29.5Z" fill="#38BDF8" />
        <path d="M29.5 18L19.5 21.2L20.8 18L19.5 14.8L29.5 18Z" fill="#E0E7FF" />
        <path d="M6.5 18L16.5 21.2L15.2 18L16.5 14.8L6.5 18Z" fill="#818CF8" />
        <circle cx="18" cy="18" r="2.2" fill="#FFFFFF" />
        <defs>
          <linearGradient id="ccBrandGrad" x1="0" y1="0" x2="36" y2="36" gradientUnits="userSpaceOnUse">
            <stop stopColor="#1E1B4B" />
            <stop offset="0.5" stopColor="#4338CA" />
            <stop offset="1" stopColor="#6366F1" />
          </linearGradient>
        </defs>
      </svg>
      <span className="flex items-baseline leading-none">
        <span className="text-[1.35rem] font-extrabold tracking-[-0.035em] text-slate-900">
          Career<span className="text-brand-600">Compass</span>
        </span>
        <span className="ml-1.5 rounded border border-brand-200 bg-brand-50 px-1.5 py-0.5 text-[0.62rem] font-bold tracking-[0.04em] text-brand-600">
          AI
        </span>
      </span>
    </span>
  );
}
