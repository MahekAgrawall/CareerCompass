interface ChipSelectProps {
  options: readonly string[];
  value: string[];
  onChange: (next: string[]) => void;
  /** Optional label renderer (defaults to the raw option). */
  idPrefix?: string;
}

/** Accessible multi-select rendered as toggleable chips. */
export default function ChipSelect({ options, value, onChange, idPrefix = "chip" }: ChipSelectProps) {
  const toggle = (option: string) => {
    onChange(value.includes(option) ? value.filter((v) => v !== option) : [...value, option]);
  };

  return (
    <div className="flex flex-wrap gap-2" role="group">
      {options.map((option) => {
        const selected = value.includes(option);
        return (
          <button
            key={option}
            id={`${idPrefix}-${option}`}
            type="button"
            aria-pressed={selected}
            onClick={() => toggle(option)}
            className={`chip ${selected ? "chip-on" : "chip-off"}`}
          >
            {selected && <span className="mr-1">✓</span>}
            {option}
          </button>
        );
      })}
    </div>
  );
}
