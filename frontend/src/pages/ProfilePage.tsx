import { useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import Alert from "@/components/Alert";
import ChipSelect from "@/components/ChipSelect";
import SelectField from "@/components/SelectField";
import type { Profile } from "@/api/types";
import { useDocumentTitle } from "@/lib/hooks";
import {
  DEFAULT_INTERESTS,
  DEFAULT_SKILLS,
  EXPERIENCE_OPTIONS,
  GRAD_YEAR_OPTIONS,
  INTEREST_OPTIONS,
  LOCATION_OPTIONS,
  SKILL_OPTIONS,
} from "@/lib/options";
import { useAuth } from "@/state/AuthContext";
import { useProfile } from "@/state/ProfileContext";

export default function ProfilePage() {
  useDocumentTitle("Candidate profile");
  const navigate = useNavigate();
  const { user } = useAuth();
  const { profile, saveProfile } = useProfile();

  const [name, setName] = useState(profile?.name || user?.name || "");
  const [gradYear, setGradYear] = useState(profile?.grad_year || GRAD_YEAR_OPTIONS[0]);
  const [experience, setExperience] = useState(profile?.experience || EXPERIENCE_OPTIONS[0]);
  const [location, setLocation] = useState(profile?.location || LOCATION_OPTIONS[0]);
  const [interests, setInterests] = useState<string[]>(
    profile?.interests?.filter((i) => (INTEREST_OPTIONS as readonly string[]).includes(i)).length
      ? profile!.interests.filter((i) => (INTEREST_OPTIONS as readonly string[]).includes(i))
      : [...DEFAULT_INTERESTS],
  );
  const [skills, setSkills] = useState<string[]>(
    profile?.current_skills?.filter((s) => (SKILL_OPTIONS as readonly string[]).includes(s)).length
      ? profile!.current_skills.filter((s) => (SKILL_OPTIONS as readonly string[]).includes(s))
      : [...DEFAULT_SKILLS],
  );
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);

    if (!name.trim()) {
      setError("Please provide your name.");
      return;
    }
    if (interests.length === 0) {
      setError("Please select at least one interest area.");
      return;
    }
    if (skills.length === 0) {
      setError("Please choose at least one skill you are familiar with.");
      return;
    }

    const next: Profile = {
      name: name.trim(),
      grad_year: gradYear,
      experience,
      location,
      current_skills: skills,
      interests,
    };

    setSaving(true);
    await saveProfile(next);
    setSaving(false);
    navigate("/matches");
  };

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="section-title">👤 Step 1 — Build Your Candidate Profile</h1>
      <p className="caption mt-1">
        Tell us about your background and interests so we can identify high-fit career trajectories.
      </p>
      <hr className="my-5 border-slate-200" />

      <form onSubmit={handleSubmit} className="space-y-5">
        <div className="grid gap-5 md:grid-cols-2">
          <div className="space-y-4">
            <label className="block">
              <span className="label">Full Name</span>
              <input
                className="input"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Mahek Agrawal"
              />
            </label>
            <SelectField label="Graduation Year" value={gradYear} options={GRAD_YEAR_OPTIONS} onChange={setGradYear} />
            <SelectField
              label="Experience Level"
              value={experience}
              options={EXPERIENCE_OPTIONS}
              onChange={setExperience}
            />
            <SelectField
              label="Preferred Work Hub"
              value={location}
              options={LOCATION_OPTIONS}
              onChange={setLocation}
            />
          </div>

          <div className="space-y-5">
            <div>
              <span className="label">
                What genuinely interests you? <span className="font-normal text-slate-500">(roles match these strictly)</span>
              </span>
              <ChipSelect options={INTEREST_OPTIONS} value={interests} onChange={setInterests} idPrefix="interest" />
            </div>
            <div>
              <span className="label">Existing Technical Skills</span>
              <ChipSelect options={SKILL_OPTIONS} value={skills} onChange={setSkills} idPrefix="skill" />
            </div>
          </div>
        </div>

        {error && <Alert tone="error">{error}</Alert>}

        <button type="submit" className="btn btn-primary w-full" disabled={saving}>
          {saving ? "Saving…" : "Find Matching Roles →"}
        </button>
      </form>

      {!user && (
        <p className="mt-4 text-center text-xs text-slate-400">
          You are browsing as a guest. <span className="font-semibold text-slate-500">Sign in</span> to save
          this profile across devices.
        </p>
      )}
    </div>
  );
}
