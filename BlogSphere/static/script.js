document.addEventListener("DOMContentLoaded", () => {
  // Ask for confirmation before a user deletes a post.
  document.querySelectorAll("form[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      const message = form.getAttribute("data-confirm") || "Are you sure?";
      if (!window.confirm(message)) {
        event.preventDefault();
      }
    });
  });

  // Avoid accidental whitespace-only comments and posts.
  document.querySelectorAll("textarea[required]").forEach((field) => {
    field.addEventListener("input", () => {
      field.setCustomValidity(field.value.trim() ? "" : "Please enter some text.");
    });
  });

  document.querySelectorAll("[data-share-url]").forEach((button) => {
    button.addEventListener("click", async () => {
      const shareData = {
        title: button.dataset.shareTitle || "BlogSphere story",
        url: button.dataset.shareUrl,
      };

      if (navigator.share) {
        try {
          await navigator.share(shareData);
        } catch (error) {
          if (error.name !== "AbortError") {
            window.alert("The story could not be shared. Please copy its link from your browser.");
          }
        }
        return;
      }

      try {
        await navigator.clipboard.writeText(shareData.url);
        button.textContent = "Link copied!";
      } catch {
        window.prompt("Copy this story link:", shareData.url);
      }
    });
  });
});
