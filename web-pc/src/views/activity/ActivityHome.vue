<template>
  <component :is="store.isStaff ? ActivityList : StudentActivities" />
</template>

<script setup>
import { useUserStore } from '@/store/user'
import ActivityList from './ActivityList.vue'
import StudentActivities from './StudentActivities.vue'

const store = useUserStore()
</script>
