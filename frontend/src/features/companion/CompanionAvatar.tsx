import { createContext, useContext, type ReactNode } from "react";
import { useCompanionPet } from "./hooks/useCompanionPet";
import { getCompanionPet, type CompanionPet } from "./lib/sprite";

const PetContext = createContext<CompanionPet>(getCompanionPet("shuangling"));

export function CompanionAvatarProvider({ userId, children }: { userId: string; children: ReactNode }) {
  const [pet] = useCompanionPet(userId);
  return <PetContext.Provider value={pet}>{children}</PetContext.Provider>;
}

/** Frame zero, cropped to the face. No timer or moving sprite in chat history. */
export function CompanionHeadAvatar({
  pet: selectedPet,
  size = 36,
}: {
  pet?: CompanionPet;
  size?: number;
} = {}) {
  const currentPet = useContext(PetContext);
  const pet = selectedPet ?? currentPet;
  const scale = size / 36;
  const cellWidth = Math.round(pet.headCrop.cellWidth * scale);
  const cellHeight = Math.round(cellWidth * 208 / 192);
  return <span className="conv-pet-head" role="img" aria-label={`${pet.displayName}头像`} style={{
    width: size,
    height: size,
    backgroundImage: `url(${pet.spritesheetUrl})`,
    backgroundSize: `${cellWidth * 8}px ${cellHeight * pet.gridRows}px`,
    backgroundPosition: `-${Math.round(pet.headCrop.left * scale)}px -${Math.round(pet.headCrop.top * scale)}px`,
  }} />;
}

export function useCompanionName() {
  return useContext(PetContext).displayName;
}
