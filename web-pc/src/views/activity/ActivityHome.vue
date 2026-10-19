<template>
  <component :is="homeComponent" />
</template>

<script setup>
import { computed } from 'vue'
import { useUserStore } from '@/store/user'
import { PERM } from '@/constants'
import ActivityList from './ActivityList.vue'
import StudentActivities from './StudentActivities.vue'

const store = useUserStore()

/** 能申办/管理活动 → 管理视图；否则学生/访客视图 */
const homeComponent = computed(() => (store.can(PERM.ACTIVITY_CREATE) ? ActivityList : StudentActivities))
</script>
