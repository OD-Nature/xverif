if vim.g.loaded_xloc_nvim then
  return
end
vim.g.loaded_xloc_nvim = true

require("xloc").setup()
