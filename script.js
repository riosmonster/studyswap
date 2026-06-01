const menuToggle = document.querySelector(".menu-toggle");
const navLinks = document.querySelector("[data-nav-links]");
const waitlistForm = document.querySelector("[data-waitlist-form]");
const formMessage = document.querySelector("[data-form-message]");

menuToggle.addEventListener("click", () => {
  const isOpen = navLinks.classList.toggle("is-open");
  menuToggle.setAttribute("aria-expanded", String(isOpen));
});

navLinks.querySelectorAll("a").forEach((link) => {
  link.addEventListener("click", () => {
    navLinks.classList.remove("is-open");
    menuToggle.setAttribute("aria-expanded", "false");
  });
});

waitlistForm.addEventListener("submit", (event) => {
  event.preventDefault();

  const formData = new FormData(waitlistForm);
  const name = String(formData.get("name") || "").trim();
  const email = String(formData.get("email") || "").trim();

  if (!name || !email) {
    formMessage.textContent = "Preencha seu nome e e-mail para entrar na lista.";
    return;
  }

  formMessage.textContent = `${name}, você entrou na lista de espera do StudySwap.`;
  waitlistForm.reset();
});
