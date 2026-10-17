export default function SelectField({
  label,
  value,
  options,
  onChange,
  hint,
}: {
  label: string;
  value: string;
  options: readonly string[];
  onChange: (value: string) => void;
  hint?: string;
}) {
  // A saved answer the vocabulary no longer offers — a work hub that was
  // retired, a profile saved against an older list — stays selectable instead of
  // leaving the control blank and silently hiding the candidate's own answer.
  const choices = value && !options.includes(value) ? [value, ...options] : options;

  return (
    <label className="block">
      <span className="label">{label}</span>
      <select className="input" value={value} onChange={(e) => onChange(e.target.value)}>
        {choices.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
      {hint && <span className="mt-1 block text-xs text-slate-500">{hint}</span>}
    </label>
  );
}
