import { useEffect, useRef, useState } from "react";
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

/** Keeps only the stored answers the questionnaire still offers. */
function pick(saved: string[] | undefined, allowed: readonly string[]): string[] | null {
  const kept = (saved ?? []).filter((value) => (allowed as readonly string[]).includes(value));
  return kept.length ? kept : null;
}

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
    () => pick(profile?.interests, INTEREST_OPTIONS) ?? [...DEFAULT_INTERESTS],
  );
  const [skills, setSkills] = useState<string[]>(
    () => pick(profile?.current_skills, SKILL_OPTIONS) ?? [...DEFAULT_SKILLS],
  );
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // A signed-in account's saved answers arrive just after the form mounts (this
  // page is the post-signup landing route), so re-seed the fields whenever the
  // resolved profile changes. Otherwise a returning candidate would see the
  // defaults — or, after switching accounts, the previous user's answers.
  const seeded = useRef<Profile | null | undefined>(undefined);
  useEffect(() => {
    if (seeded.current === profile) return;
    seeded.current = profile;
    setName(profile?.name || user?.name || "");
    setGradYear(profile?.grad_year || GRAD_YEAR_OPTIONS[0]);
    setExperience(profile?.experience || EXPERIENCE_OPTIONS[0]);
    setLocation(profile?.location || LOCATION_OPTIONS[0]);
    setInterests(pick(profile?.interests, INTEREST_OPTIONS) ?? [...DEFAULT_INTERESTS]);
    setSkills(pick(profile?.current_skills, SKILL_OPTIONS) ?? [...DEFAULT_SKILLS]);
  }, [profile, user]);

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
