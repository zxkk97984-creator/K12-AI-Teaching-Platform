import { COMPANION_PETS, getSpriteStyle, type CompanionPetId } from "./lib/sprite";

const PREVIEW_WIDTH = 76;
const PREVIEW_HEIGHT = Math.round(PREVIEW_WIDTH * 208 / 192);

export function CompanionPetPicker({
  value,
  onChange,
  disabled = false,
}: {
  value: CompanionPetId;
  onChange: (petId: CompanionPetId) => void;
  disabled?: boolean;
}) {
  return <fieldset className="settings-pet-picker" disabled={disabled}>
    <legend>选择桌宠形象</legend>
    <div className="settings-pet-grid">
      {COMPANION_PETS.map((pet) => <label
        key={pet.id}
        className={"settings-pet-option" + (value === pet.id ? " is-selected" : "")}
        title={pet.description}
      >
        <input
          type="radio"
          name="companion_pet_id"
          value={pet.id}
          aria-label={pet.displayName}
          checked={value === pet.id}
          onChange={() => onChange(pet.id)}
        />
        <span
          className="settings-pet-preview"
          aria-hidden="true"
          style={{
            ...getSpriteStyle("idle", 0, PREVIEW_WIDTH, pet.id),
            width: PREVIEW_WIDTH,
            height: PREVIEW_HEIGHT,
          }}
        />
        <strong>{pet.displayName}</strong>
      </label>)}
    </div>
  </fieldset>;
}
