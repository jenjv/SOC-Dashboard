<script setup>
import { RouterView } from 'vue-router'
</script>

<template>
  <RouterView />
</template>

<style>
* {
  box-sizing: border-box;
}

html,
body,
#app {
  min-width: 320px;
  min-height: 100%;
  margin: 0;
}

body {
  display: block;
  min-height: 100vh;
}

#app {
  display: block;
  width: 100%;
  max-width: none;
  min-height: 100vh;
  margin: 0;
  padding: 0;
}

button,
input,
select {
  font: inherit;
}
</style>