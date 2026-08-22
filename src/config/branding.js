export const branding = {
  productName: import.meta.env.VITE_PRODUCT_NAME || "EAY One",
  companyName: import.meta.env.VITE_COMPANY_NAME || "EAY",
  loginImage: import.meta.env.VITE_LOGIN_IMAGE || "",
  showEntranceScene:
    String(import.meta.env.VITE_SHOW_ENTRANCE_SCENE || "false").toLowerCase() === "true",
  slogan: "Operasyonu tek merkezden yönetin.",
};
