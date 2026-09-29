import { useCallback, useEffect, useState } from "react";
import { getCompanionPet } from "../lib/sprite";
import { getMe, patchPreferences } from "../../identity/api";
import { useAccount } from "../../identity/AccountContext";
const EVENT = "companion:pet-changed";
export function useCompanionPet(userId: string) {
  const account = useAccount();
  const [pet, setPet] = useState(() => getCompanionPet(account?.preferences?.companion_pet_id ?? ""));
  useEffect(() => { setPet(getCompanionPet(account?.preferences?.companion_pet_id ?? "")); }, [account?.preferences?.companion_pet_id, userId]);
  useEffect(() => {
    const onChange = (event: Event) => {
      const detail = (event as CustomEvent<{ userId: string; petId: string }>)
        .detail;
      if (detail?.userId === userId) setPet(getCompanionPet(detail.petId));
    };
    window.addEventListener(EVENT, onChange);
    return () => window.removeEventListener(EVENT, onChange);
  }, [userId]);
  const select = useCallback(
    async (id: string) => {
      const selected = getCompanionPet(id);
      const me = await getMe();
      if (me.user.id !== userId || !me.profile) throw new Error("账号已切换，请重新选择桌宠");
      await patchPreferences({ base_revision: me.profile.revision, companion_pet_id: selected.id });
      setPet(selected);
      window.dispatchEvent(
        new CustomEvent(EVENT, { detail: { userId, petId: selected.id } }),
      );
    }, [userId],
  );
  return [pet, select] as const;
}
